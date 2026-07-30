from sql_pilot_engine.llm.json_repair import JSONRepairer

class MockRepairLLM:
    def complete(self, prompt: str) -> str:
        assert "修复内容" in prompt
        assert "合法 JSON object" in prompt

        return """
        {
          "sql_summary": "修复后的 JSON",
          "main_tables": [],
          "output_columns": [],
          "cte_steps": [],
          "cte_dependencies": [],
          "suspicious_points": [],
          "uncertainties": [],
          "route_signals": {
            "need_metadata": false,
            "need_rag": false,
            "need_review": true,
            "need_human_confirm": false,
            "can_auto_fix": false,
            "next_node": "review_agent"
          }
        }
"""

def test_json_repairer_should_return_repaired_text():
    
    repairer = JSONRepairer(llm_client=MockRepairLLM())

    repaired = repairer.repair(
        broken_text="sql summary: 修复后的 JSON",
        schema_hint='{"sql_summary":"string"}',
    )

    assert "sql_summary" in repaired
    assert "修复后的 JSON" in repaired