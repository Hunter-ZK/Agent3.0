from __future__ import annotations

from sql_pilot_engine.analysis.facts import SQLFacts


from sql_pilot_engine.core.enums import IssueAction,IssueSource,Severity

from sql_pilot_engine.core.models import Issue

from sql_pilot_engine.metadata.models import MetadataLookupStatus, TableLookupResult

from sql_pilot_engine.metadata.provider import MetadataProvider



class MetadataValidator:
    """根据SQLFacts和元数据校验表字段引用。

    设计原则：
    只验证能够明确解析归属的字段。
    遇到多表未限定字段时，不进行主观猜测，
    避免产生错误告警。
    """
    
    def validate(
        self,
        *,
        facts: SQLFacts,
        provider: MetadataProvider,
    ) -> list[Issue]:
        """验证SQL引用的物理表及可明确归属的字段。

        本方法先统一查询源表和目标表，
        再使用同一份请求内缓存校验字段。

        同一张表在一次validate调用中只查询一次。
        """

        issues: list[Issue] = []

        table_cache: dict[
            str,
            TableLookupResult,
        ] = {}

        # source_tables和target_tables可能出现重复。
        # dict.fromkeys既能去重，也能保持原顺序。
        table_names = tuple(
            dict.fromkeys(
                (
                    *facts.source_tables,
                    *facts.target_tables,
                )
            )
        )

        for table_name in table_names:
            lookup = provider.get_table(
                table_name
            )

            table_cache[table_name] = lookup

            issues.extend(
                self._validate_table_lookup(
                    table_name=table_name,
                    lookup=lookup,
                )
            )

        issues.extend(
            self._validate_columns(
                facts=facts,
                table_cache=table_cache,
            )
        )

        return issues
    
    def _validate_table_lookup(
        self,
        *,
        table_name: str,
        lookup: TableLookupResult,
    ) -> list[Issue]:
        """将表查询状态转化为结构化Issue"""
        
        if lookup.status == MetadataLookupStatus.FOUND:
            return []
        
        if lookup.status == MetadataLookupStatus.ERROR:
            return [
                Issue(
                    rule_id="METADATA_LOOKUP_FAILED",
                    title="元数据查询失败",
                    severity=Severity.MEDIUM,
                    message=(
                        f"无法查询表 {table_name} 的元数据："
                        f"{lookup.error_message or 'unknown error'}"
                    ),
                    suggestion=(
                        "请检查元数据服务、权限或网络状态。"
                    ),
                    evidence=table_name,
                    category="metadata",
                    source=IssueSource.SYSTEM,
                    confidence=1.0,
                    action=IssueAction.CONTEXT_REQUIRED,
                    auto_fixable=False,
                    requires_metadata=True,
                )
            ]

        return [
            Issue(
                rule_id="TABLE_NOT_FOUND",
                title="引用的物理表不存在",
                severity=Severity.HIGH,
                message=(
                    f"元数据中未找到物理表：{table_name}"
                ),
                suggestion=(
                    "请检查表名、项目名、数据库名或环境配置。"
                ),
                evidence=table_name,
                category="metadata",
                source=IssueSource.SYSTEM,
                confidence=1.0,
                action=IssueAction.BLOCK,
                auto_fixable=False,
                requires_metadata=False,
            )
        ]
            
    def _validate_columns(
        self,
        *,
        facts: SQLFacts,
        table_cache: dict[
            str,
            TableLookupResult,
        ],
    ) -> list[Issue]:
        """验证能够明确归属到物理表的字段。"""

        issues: list[Issue] = []

        alias_map = self._build_alias_map(facts)

        for column in facts.column_references:
            # SELECT产生的表达式别名不是物理字段。
            if column.name in facts.select_aliases:
                continue

            table_name = self._resolve_column_table(
                facts=facts,
                qualifier=column.qualifier,
                alias_map=alias_map,
            )

            # 无法明确归属时不猜测。
            if table_name is None:
                continue

            lookup = table_cache.get(table_name)

            if (
                lookup is None
                or lookup.status
                != MetadataLookupStatus.FOUND
                or lookup.table is None
            ):
                continue

            if (
                lookup.table.get_column(column.name)
                is not None
            ):
                continue

            issues.append(
                Issue(
                    rule_id="COLUMN_NOT_FOUND",
                    title="引用的字段不存在",
                    severity=Severity.HIGH,
                    message=(
                        f"表 {table_name} 中不存在字段 "
                        f"{column.name}"
                    ),
                    suggestion=(
                        "请检查字段拼写，或重新获取最新元数据。"
                    ),
                    evidence=(
                        f"{column.qualifier + '.' if column.qualifier else ''}"
                        f"{column.name}"
                    ),
                    category="metadata",
                    source=IssueSource.SYSTEM,
                    confidence=1.0,
                    action=IssueAction.BLOCK,
                    auto_fixable=False,
                    requires_metadata=False,
                    metadata={
                        "table_name": table_name,
                        "column_name": column.name,
                    },
                )
            )

        return issues
    
        
    @staticmethod
    def _build_alias_map(
        facts: SQLFacts,
    ) -> dict[str, str]:
        """建立限定符到物理表的映射。

        示例：
        dwd_order_detail o

        映射结果：
        o -> dwd_order_detail
        dwd_order_detail -> dwd_order_detail
        """

        alias_map: dict[str, str] = {}

        for reference in facts.table_references:
            physical_name = reference.physical_name

            alias_map[physical_name] = physical_name

            short_name = physical_name.rsplit(
                ".",
                maxsplit=1,
            )[-1]

            alias_map[short_name] = physical_name

            if reference.alias:
                alias_map[
                    reference.alias
                ] = physical_name

        return alias_map


    @staticmethod
    def _resolve_column_table(
        *,
        facts: SQLFacts,
        qualifier: str | None,
        alias_map: dict[str, str],
    ) -> str | None:
        """确定字段属于哪张物理表。

        有限定符：
            o.user_id -> 通过alias_map解析。

        无限定符：
            单表且无CTE时可以安全归属。

        多表、CTE场景：
            不进行猜测，等待后续作用域分析。
        """

        if qualifier:
            if qualifier in facts.cte_names:
                return None

            return alias_map.get(qualifier)

        if (
            len(facts.source_tables) == 1
            and not facts.cte_names
        ):
            return facts.source_tables[0]

        return None
