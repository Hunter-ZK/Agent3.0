from __future__ import annotations
from dataclasses import dataclass
from sqlglot import exp
from sql_pilot_engine.analysis.sql_parser import SQLParseResult


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
    cte_names: tuple[str, ...]
    
    has_select_star: bool
    has_drop: bool
    has_truncate: bool
    has_write_operation: bool
    

class SQLFactsExtractor:
    """将SQLGlot AST转换成项目内部的SQLFacts。

    设计原因：
    - Rule不应直接依赖SQLGlot的全部API；
    - SQLGlot版本变化时，主要修改本类；
    - Metadata、RAG和Rule可以共享同一份结果；
    - 避免每条规则重复解析SQL。
    """
    
    WRITE_OOPERATION_TYPES = {
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
        
        has_select_star = False
        
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
                target_tables=target_tables,
            )
            source_tables.update(current_sources)
            
            if self._contains_select_star(statement):
                has_select_star = True
                
        statement_type_set = set(statement_types)
        
        return SQLFacts(
            statement_count=(
                parse_result.statements
            ),
            statement_types=tuple(statement_types),
            source_tables=tuple(sorted(source_tables)),
            target_tables=tuple(sorted(target_tables)),
            cte_names=tuple(sorted(cte_names)),
            has_select_star=has_select_star,
            has_drop="drop" in statement_type_set,
            has_truncate=any(
                item.startswith("truncate")
                for item in statement_type_set
            ),
            has_write_operation=bool(
                statement_type_set
                & self.WRITE_OOPERATION_TYPES
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
        """提取INSERT语句的目标表。

        statement.this表示当前语句的主体对象。
        对Insert而言，this通常是写入的目标Table。
        """
        
        targets: set[str] = set()
        
        if isinstance(statement, exp.Insert):
            target = statement.this
            
            if isinstance(target, exp.Table):
                targets.add(
                    self._qualified_table_name(target)
                )
                
        return targets
    
    
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