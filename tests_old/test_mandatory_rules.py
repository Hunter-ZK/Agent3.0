from sql_pilot_engine.context.builder import (
    QueryContextBuilder,
)
from sql_pilot_engine.context.mandatory_rules import (
    MandatoryBusinessRule,
    MandatoryRuleMatcher,
)
from sql_pilot_engine.context.models import (
    ContextDocument,
    ContextDocumentKind,
    RetrievedDocument,
)


CURRENT_PERIOD_RULE = (
    MandatoryBusinessRule(
        rule_id="current_period",

        triggers=(
            "本期",
        ),

        text=(
            "本期使用dt当前期参数。"
        ),
    )
)


def build_retrieved(
    *,
    document_id: str,
    text: str,
) -> RetrievedDocument:

    return RetrievedDocument(
        document=ContextDocument(
            document_id=document_id,

            kind=(
                ContextDocumentKind
                .BUSINESS_KNOWLEDGE
            ),

            text=text,

            metadata={},
        ),

        score=0.5,
    )


def test_mandatory_rule_is_added():

    builder = QueryContextBuilder(
        mandatory_rule_matcher=(
            MandatoryRuleMatcher(
                (
                    CURRENT_PERIOD_RULE,
                )
            )
        )
    )

    context = builder.build(
        question=(
            "统计本期绿色贷款余额"
        ),

        business_knowledge=[],

        verified_sql=[],
    )

    assert (
        len(
            context.business_knowledge
        )
        == 1
    )

    assert (
        context
        .business_knowledge[0]
        .document
        .document_id
        == "current_period"
    )


def test_rule_not_added_without_trigger():

    builder = QueryContextBuilder(
        mandatory_rule_matcher=(
            MandatoryRuleMatcher(
                (
                    CURRENT_PERIOD_RULE,
                )
            )
        )
    )

    context = builder.build(
        question=(
            "统计绿色贷款余额"
        ),

        business_knowledge=[],

        verified_sql=[],
    )

    assert (
        context.business_knowledge
        == ()
    )


def test_mandatory_rule_deduplicates_rag_result():

    builder = QueryContextBuilder(
        mandatory_rule_matcher=(
            MandatoryRuleMatcher(
                (
                    CURRENT_PERIOD_RULE,
                )
            )
        )
    )

    context = builder.build(
        question=(
            "统计本期绿色贷款余额"
        ),

        business_knowledge=[
            build_retrieved(
                document_id=(
                    "current_period"
                ),

                text=(
                    "RAG中的同一条规则"
                ),
            )
        ],

        verified_sql=[],
    )

    assert (
        len(
            context.business_knowledge
        )
        == 1
    )

    assert (
        context
        .business_knowledge[0]
        .document
        .text
        == (
            "本期使用dt当前期参数。"
        )
    )