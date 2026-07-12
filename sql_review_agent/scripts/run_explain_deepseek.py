from dotenv import load_dotenv

from sql_review_agent.agents.sql_explain_agent import SQLExplainAgent
from sql_review_agent.llm.deepseek_client import DeepSeekLLMClient
from sql_review_agent.schemas.requests import SQLExplainRequest


def main():
    load_dotenv()

    agent = SQLExplainAgent(
        llm_client=DeepSeekLLMClient.from_env()
    )

    request = SQLExplainRequest(
        sql="""
        select user_id, sum(amount) as total_amt
        from dwd_order
        where dt = '${bizdate}'
        group by user_id
        """,
        file_path="manual_deepseek.sql",
    )

    response = agent.explain(request, trace_id="manual-trace-001")

    print(response.to_dict())


if __name__ == "__main__":
    main()