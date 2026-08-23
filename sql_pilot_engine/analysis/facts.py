from __future__ import annotations
from dataclasses import dataclass
from sqlglot import exp
from sql_pilot_engine.analysis.sql_parser import SQLParseResult

@dataclass(frozen=True)
class TableReference:
    """SQL出现的一次物理表引用"""
    
    physical_name: str
    alias: str | None = None

@dataclass(frozen=True)
class ColumnReference:
    """SQL中出现的一次字段引用。

    qualifier是字段前面的限定符：

    o.order_id
    → qualifier="o"
    → name="order_id"

    user_id
    → qualifier=None
    → name="user_id"
    """

    name: str
    qualifier: str | None = None


@dataclass(frozen=True)
class SQLFacts:
    """从SQL AST中提取的稳定事实。

    为什么使用 frozen=True：
    Facts 是解析阶段产生的只读结果。
    后续规则只能读取，不能在运行过程中修改它，
    避免前一条规则影响后一条规则。

    为什么使用 tuple 而不是 list：
    tuple 本身不可变，更符合“只读事实”的语义。
    """
    statement_count: int
    statement_types: tuple[str, ...]
    
    source_tables: tuple[str, ...]
    target_tables: tuple[str, ...]
    insert_target_table: str | None
    referenced_tables: tuple[str, ...]
    cte_names: tuple[str, ...]
    
    table_references: tuple[TableReference, ...]
    column_references: tuple[ColumnReference, ...]
    select_aliases: tuple[str, ...]
    
    has_select_star: bool
    has_drop: bool
    has_truncate: bool
    has_write_operation: bool
    has_partition_clause: bool

class SQLFactsExtractor:
    """将SQLGlot AST转换成项目内部的SQLFacts。

    设计原因：
    - Rule不应直接依赖SQLGlot的全部API；
    - SQLGlot版本变化时，主要修改本类；
    - Metadata、RAG和Rule可以共享同一份结果；
    - 避免每条规则重复解析SQL。
    """
    
    WRITE_OPERATION_TYPES = {
        "insert",
        "update",
        "delete",
        "merge",
        "create",
        "drop",
        "truncate",
        "alter",
    }
    
    def extract(
        self,
        parse_result: SQLParseResult,
    ) -> SQLFacts:
        """从一次成功的解析结果中提取事实。

        SQLParseResult.success=False 时没有可信AST，
        因此调用方必须先处理解析失败，不能继续提取Facts。
        """
        
        if not parse_result.success:
            raise ValueError(
                "Cannot extract SQL facts from "
                "a failed parse result."
            )
            
        statement_types: list[str] = []
        source_tables: set[str] = set()
        target_tables: set[str] = set()
        cte_names: set[str] = set()
        
        table_references: set[TableReference] = set()
        column_references: set[ColumnReference] = set()
        select_aliases: set[str] = set()
        
        has_select_star = False
        
        insert_targets: list[str] = []
        insert_partition_flags: list[bool] = []
        for statement in parse_result.statements:
            # print(statement)
            statement_type = statement.key.lower()
            # print(statement_type)
            statement_types.append(statement_type)
            
            current_cte_names = self._extract_cte_names(statement)
            
            cte_names.update(current_cte_names)
            
            current_targets = self._extract_targets(statement)
            
            target_tables.update(current_targets)
            
            current_sources = self._extract_sources(
                statement=statement,
                cte_names=current_cte_names,
                target_tables=current_targets,
            )
            source_tables.update(current_sources)
            
            current_table_references = (
                self._extract_table_references(
                    statement=statement,
                    cte_names=current_cte_names,
                    target_tables=current_targets,
                )
            )
            
            (
                current_insert_target,
                current_has_partition,
            ) = self._extract_insert_facts(
                statement
            )

            if current_insert_target is not None:
                insert_targets.append(
                    current_insert_target
                )

                insert_partition_flags.append(
                    current_has_partition
                )
                        
            table_references.update(current_table_references)
            
            column_references.update(self._extract_column_references(statement))
            
            select_aliases.update(self._extract_select_aliases(statement))
            
            if self._contains_select_star(statement):
                has_select_star = True
                
        statement_type_set = set(statement_types)

        referenced_tables = tuple(
            sorted(
                source_tables
                | target_tables
            )
        )

        # 当前 SQLFacts 的 insert_target_table
        # 是单值 Contract。
        #
        # 因此只有 SQL 中存在唯一 INSERT Target 时，
        # 才能安全暴露该 Fact。
        #
        # 多 INSERT 不能随便取第一张或最后一张表，
        # 否则 Metadata Rule 可能校验错误的目标表。
        if len(insert_targets) == 1:
            insert_target_table = (
                insert_targets[0]
            )

            has_partition_clause = (
                insert_partition_flags[0]
            )

        else:
            insert_target_table = None
            has_partition_clause = False


        return SQLFacts(
            statement_count=(
                parse_result.statement_count
            ),
            statement_types=tuple(statement_types),
            source_tables=tuple(sorted(source_tables)),
            target_tables=tuple(sorted(target_tables)),
            referenced_tables=tuple(sorted(referenced_tables)),
            insert_target_table=(
                insert_target_table
            ),
            cte_names=tuple(sorted(cte_names)),
            table_references=tuple(
                sorted(
                    table_references,
                    key=lambda item:(
                        item.physical_name,
                        item.alias or ""
                    )
                )
            ),
            column_references=tuple(
                sorted(
                    column_references,
                    key=lambda item: (
                        item.qualifier or "",
                        item.name,
                    )
                )
            ),
            select_aliases=tuple(
                sorted(select_aliases)
            ),
            has_select_star=has_select_star,
            has_drop="drop" in statement_type_set,
            has_truncate=any(
                item.startswith("truncate")
                for item in statement_type_set
            ),
            has_write_operation=bool(
                statement_type_set
                & self.WRITE_OPERATION_TYPES
            ),

            has_partition_clause=(
                has_partition_clause
            ),
        )
        
    def _extract_cte_names(
        self,
        statement: exp.Expression,
    ) -> set[str]:
        """提取WITH语句中定义的CTE名称。

        CTE在AST中也可能表现为Table引用。
        如果不先识别CTE，系统会把临时结果集误判为物理表，
        进而错误查询元数据或知识库。
        """
        
        return {
            cte.alias_or_name.lower()
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        
    def _extract_targets(
        self,
        statement: exp.Expression,
    ) -> set[str]:

        if not isinstance(
            statement,
            exp.Insert,
        ):
            return set()

        target_table = (
            self._extract_insert_target_table(
                statement
            )
        )

        if target_table is None:
            return set()

        return {
            target_table
        }

    def _extract_insert_target_table(
        self,
        insert: exp.Insert,
    ) -> str | None:

        target = insert.this

        if isinstance(
            target,
            exp.Schema,
        ):
            target = target.this

        if not isinstance(
            target,
            exp.Table,
        ):
            return None

        return self._qualified_table_name(
            target
        )
    
    def _extract_sources(
        self,
        *,
        statement: exp.Expression,
        cte_names: set[str],
        target_tables: set[str],
    ) -> set[str]:
        """提取物理源表，排除CTE和INSERT目标表。"""
        
        sources: set[str] = set()
        
        for table in statement.find_all(exp.Table):
            table_name = self._qualified_table_name(
                table
            )
            
            if table.name.lower() in cte_names:
                continue
            
            if table_name in target_tables:
                continue
            
            sources.add(table_name)
            
        return sources
    

    def _extract_table_references(
        self,
        *,
        statement: exp.Expression,
        cte_names: set[str],
        target_tables: set[str],
    ) -> set[TableReference]:
        """提取物理表及其别名"""
        
        references: set[TableReference] = set()
        
        for table in statement.find_all(exp.Table):
            physical_name = self._qualified_table_name(table)
            
            if physical_name in cte_names:
                continue
            
            if physical_name in target_tables:
                continue
            
            alias = (
                table.alias.lower()
                if table.alias
                else None
            )

            references.add(
                TableReference(
                    physical_name=physical_name,
                    alias=alias,
                )
            )
            
        return references
    

    def _extract_column_references(
        self,
        statament: exp.Expression,
    ) -> set[ColumnReference]:
        """提取SQL中使用的字段。

        exp.Column可以表示：
        - user_id
        - o.user_id
        - table_name.*
        
        星号不参与字段存在性校验，因此直接跳过。
        """
        
        references: set[ColumnReference] = set()
       
        for column in statament.find_all(exp.Column):
            column_name = column.name.lower()
            
            if column_name == "*":
                continue
                
            qualifier = (
                column.table.lower()
                if column.table
                else None
            )
            
            references.add(
                ColumnReference(
                    name = column_name,
                    qualifier=qualifier,
                )
            )
            
        return references
    
    
    def _extract_select_aliases(
        self,
        statement: exp.Expression,
    ) -> set[str]:
        """提取SELECT表达式产生的结果别名。

        示例：
        SUM(order_amount) AS total_amount

        ORDER BY total_amount中的total_amount
        不是物理字段，因此元数据校验应排除。
        """
        
        aliases: set[str] = set()
        for select in statement.find_all(exp.Select):

            for projection in select.expressions:
                alias = projection.alias
                
                if alias: 
                    aliases.add(alias.lower())
        
        return aliases


    def _contains_select_star(
        self,
        statement: exp.Expression,
    ) -> bool:
        """判断投影字段中是否存在SELECT *或table.*。

        不能简单查找所有exp.Star：
        COUNT(*)内部也有Star，但它不是SELECT *问题。
        因此这里只检查Select.expressions，即SELECT后面的投影项。
        """
        
        for select in statement.find_all(exp.Select):
            for projection in select.expressions:
                if isinstance(projection, exp.Star):
                    return True
                
                if (isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star,)):
                    return True
                
        return False
    
    @staticmethod
    def _qualified_table_name(
        table: exp.Table,
    ) -> str:
        """将catalog、database、table组合成完整名称。

        示例：
        project_name.database_name.order_detail
        """
        
        parts = [
            table.catalog,
            table.db,
            table.name,
        ]
        
        return ".".join(
            part.lower()
            for part in parts
            if part
        )
            
    def _extract_insert_facts(
        self,
        expression: exp.Expression,
    ) -> tuple[
        str | None,
        bool,
    ]:

        insert = (
            expression
            if isinstance(
                expression,
                exp.Insert,
            )
            else expression.find(
                exp.Insert
            )
        )

        if insert is None:
            return (
                None,
                False,
            )

        has_partition_clause = (
            insert.args.get(
                "partition"
            )
            is not None
        )

        target_table = (
            self._extract_insert_target_table(
                insert
            )
        )

        return (
            target_table,
            has_partition_clause,
        )