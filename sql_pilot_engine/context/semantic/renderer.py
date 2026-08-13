from __future__ import annotations

from sql_pilot_engine.context.semantic.models import (
    SemanticModel,
)


class SemanticModelRenderer:
    
    def render(
        self,
        model: SemanticModel,
    ) -> str:
        
        lines: list[str] = []
        
        for table in model.tables:
            
            lines.append(
                f"TABLE {table.name}:"
                f"{table.description}"
            )
            
            for column in table.columns:
                
                synonyms = ", ".join(
                    column.synonyms`
                )
                
                lines.append(
                    f" COLUMN {column.name} "
                    f"[{column.data_type}]: "
                    f"{column.description}; "
                    f"synonyms=[{synonyms}]"
                )
                
        
        for metric in model.metrics:
            
            synonyms = ", ".join(
                metric.synonyms
            )
            
            lines.append(
                f"METRIC {metric.name}: "
                f"{metric.description}; "
                f"table={metric.table}; "
                f"expression={metric.expression}; "
                f"synonyms=[{synonyms}]"   
            )
            
        return "\n".join(lines)