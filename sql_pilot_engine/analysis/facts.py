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

SQLLiteralValue = (
    str
    | int
    | float
    | bool
    | None
)


@dataclass(frozen=True)
class AggregateFact:
    """
    SQL 中一个能够确定识别的聚合事实。

    function:
        sum / avg / count /
        count_distinct 等。

    column:
        聚合对象是单一物理字段时记录。
        对复杂表达式，例如：
            SUM(amount * rate)
        column=None。

    这是刻意保守的：
    无法形式化证明时，不假装确定。
    """

    function: str

    column: (
        ColumnReference | None
    ) = None

    distinct: bool = False


@dataclass(frozen=True)
class PredicateFact:
    """
    WHERE 中能够确定提取的简单谓词。

    示例：

        dt = '202607'

        PredicateFact(
            column=ColumnReference(
                name="dt",
            ),
            operator="eq",
            values=("202607",),
        )

    当前只负责事实抽取，
    不判断这个过滤条件业务上是否正确。
    """

    column: ColumnReference

    operator: str

    values: tuple[
        SQLLiteralValue,
        ...
    ]

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
    
    aggregate_facts: tuple[
        AggregateFact,
        ...
    ] = ()

    predicate_facts: tuple[
        PredicateFact,
        ...
    ] = ()

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

        aggregate_facts: set[
            AggregateFact
        ] = set()

        predicate_facts: set[
            PredicateFact
        ] = set()
        
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

            aggregate_facts.update(
                self._extract_aggregate_facts(
                    statement
                )
            )

            predicate_facts.update(
                self._extract_predicate_facts(
                    statement
                )
            )

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
            aggregate_facts=tuple(
                sorted(
                    aggregate_facts,

                    key=lambda item: (
                        item.function,

                        (
                            item.column.qualifier
                            if (
                                item.column
                                and item.column.qualifier
                            )
                            else ""
                        ),

                        (
                            item.column.name
                            if item.column
                            else ""
                        ),
                    ),
                )
            ),

            predicate_facts=tuple(
                sorted(
                    predicate_facts,

                    key=lambda item: (
                        item.column.qualifier
                        or "",

                        item.column.name,

                        item.operator,

                        tuple(
                            str(value)
                            for value
                            in item.values
                        ),
                    ),
                )
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
    

    def _extract_aggregate_facts(
        self,
        statement: exp.Expression,
    ) -> set[AggregateFact]:
        """
        提取可形式化识别的聚合事实。

        当前只把：

            SUM(column)
            AVG(column)
            COUNT(column)
            COUNT(DISTINCT column)

        这类简单聚合绑定到具体字段。

        对：

            SUM(a * b)
            SUM(COALESCE(a, 0))

        仍然记录聚合函数，
        但 column=None。

        后续 Deterministic Rule
        因此不会对复杂表达式作过度推断。
        """

        facts: set[
            AggregateFact
        ] = set()

        for aggregate in (
            statement.find_all(
                exp.AggFunc
            )
        ):

            function = (
                aggregate.key
                .strip()
                .lower()
            )

            argument = (
                aggregate.args.get(
                    "this"
                )
            )

            distinct = bool(
                aggregate.args.get(
                    "distinct"
                )
            )

            # SQLGlot 对：
            #
            # COUNT(DISTINCT column)
            #
            # 可能将 DISTINCT 表示为
            # argument 本身。
            if isinstance(
                argument,
                exp.Distinct,
            ):

                distinct = True

                expressions = tuple(
                    argument.expressions
                )

                argument = (
                    expressions[0]
                    if len(expressions) == 1
                    else None
                )

            column = (
                self._to_column_reference(
                    argument
                )
            )

            normalized_function = (
                "count_distinct"
                if (
                    function == "count"
                    and distinct
                )
                else function
            )

            facts.add(
                AggregateFact(
                    function=(
                        normalized_function
                    ),

                    column=column,

                    distinct=distinct,
                )
            )

        return facts

    def _extract_predicate_facts(
        self,
        statement: exp.Expression,
    ) -> set[PredicateFact]:
        """
        只从 WHERE 中提取能够确定识别的简单谓词。

        当前支持：

            =
            !=
            >
            >=
            <
            <=
            IN
            BETWEEN

        不处理：
            JOIN ON
            任意函数计算
            column = another_column
            subquery predicate

        这些后续需要 Scope / Lineage
        时再扩展，不在 V1 猜测。
        """

        facts: set[
            PredicateFact
        ] = set()

        binary_types = (
            (exp.EQ, "eq"),
            (exp.NEQ, "neq"),
            (exp.GT, "gt"),
            (exp.GTE, "gte"),
            (exp.LT, "lt"),
            (exp.LTE, "lte"),
        )

        for where in (
            statement.find_all(
                exp.Where
            )
        ):

            for (
                expression_type,
                operator,
            ) in binary_types:

                for predicate in (
                    where.find_all(
                        expression_type
                    )
                ):

                    fact = (
                        self
                        ._extract_binary_predicate(
                            predicate=predicate,
                            operator=operator,
                        )
                    )

                    if fact is not None:
                        facts.add(
                            fact
                        )

            for predicate in (
                where.find_all(
                    exp.In
                )
            ):

                # NOT IN 不能错误记录成 IN。
                if isinstance(
                    predicate.parent,
                    exp.Not,
                ):
                    continue

                column = (
                    self._to_column_reference(
                        predicate.this
                    )
                )

                if column is None:
                    continue

                expressions = tuple(
                    predicate.expressions
                )

                if not expressions:
                    continue

                values: list[
                    SQLLiteralValue
                ] = []

                supported = True

                for expression in (
                    expressions
                ):

                    (
                        is_literal,
                        value,
                    ) = self._literal_value(
                        expression
                    )

                    if not is_literal:
                        supported = False
                        break

                    values.append(
                        value
                    )

                if not supported:
                    continue

                facts.add(
                    PredicateFact(
                        column=column,
                        operator="in",
                        values=tuple(
                            values
                        ),
                    )
                )

            for predicate in (
                where.find_all(
                    exp.Between
                )
            ):

                column = (
                    self._to_column_reference(
                        predicate.this
                    )
                )

                if column is None:
                    continue

                low = predicate.args.get(
                    "low"
                )

                high = predicate.args.get(
                    "high"
                )

                (
                    low_supported,
                    low_value,
                ) = self._literal_value(
                    low
                )

                (
                    high_supported,
                    high_value,
                ) = self._literal_value(
                    high
                )

                if not (
                    low_supported
                    and high_supported
                ):
                    continue

                facts.add(
                    PredicateFact(
                        column=column,

                        operator="between",

                        values=(
                            low_value,
                            high_value,
                        ),
                    )
                )

        return facts

    def _extract_binary_predicate(
        self,
        *,
        predicate: exp.Expression,
        operator: str,
    ) -> PredicateFact | None:

        left = predicate.args.get(
            "this"
        )

        right = predicate.args.get(
            "expression"
        )

        left_column = (
            self._to_column_reference(
                left
            )
        )

        right_column = (
            self._to_column_reference(
                right
            )
        )

        (
            right_is_literal,
            right_value,
        ) = self._literal_value(
            right
        )

        if (
            left_column is not None
            and right_is_literal
        ):

            return PredicateFact(
                column=left_column,
                operator=operator,
                values=(
                    right_value,
                ),
            )

        (
            left_is_literal,
            left_value,
        ) = self._literal_value(
            left
        )

        if (
            right_column is not None
            and left_is_literal
        ):

            reversed_operator = {
                "eq": "eq",
                "neq": "neq",
                "gt": "lt",
                "gte": "lte",
                "lt": "gt",
                "lte": "gte",
            }[operator]

            return PredicateFact(
                column=right_column,

                operator=(
                    reversed_operator
                ),

                values=(
                    left_value,
                ),
            )

        return None


    @staticmethod
    def _to_column_reference(
        expression: (
            exp.Expression | None
        ),
    ) -> ColumnReference | None:

        if not isinstance(
            expression,
            exp.Column,
        ):
            return None

        if expression.name == "*":
            return None

        return ColumnReference(
            name=(
                expression.name
                .strip()
                .lower()
            ),

            qualifier=(
                expression.table
                .strip()
                .lower()
                if expression.table
                else None
            ),
        )


    @staticmethod
    def _literal_value(
        expression: (
            exp.Expression | None
        ),
    ) -> tuple[
        bool,
        SQLLiteralValue,
    ]:
        """
        第一个返回值说明：
        当前 Expression 是否真的是
        可确定识别的 Literal。

        因为 None 本身可以代表 SQL NULL，
        所以不能用 None 作为“不支持”的标记。
        """

        if isinstance(
            expression,
            exp.Null,
        ):
            return (
                True,
                None,
            )

        if isinstance(
            expression,
            exp.Boolean,
        ):
            return (
                True,
                bool(
                    expression.this
                ),
            )

        if not isinstance(
            expression,
            exp.Literal,
        ):
            return (
                False,
                None,
            )

        raw = str(
            expression.this
        )

        if expression.is_string:
            return (
                True,
                raw,
            )

        try:
            return (
                True,
                int(raw),
            )

        except ValueError:
            pass

        try:
            return (
                True,
                float(raw),
            )

        except ValueError:
            return (
                True,
                raw,
            )


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