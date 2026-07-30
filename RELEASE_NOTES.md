# SQLPilot Latest Source Release Notes

## Package Version

`sqlpilot-latest-source`，基于本次对话最终项目状态整理。

## Included

- Latest source code for `sql_review_agent`
- v2.5-final-migration features:
  - SQL lightweight analysis
  - LLM context builder
  - strict LLM Review schema + repair
  - Auto Fix / Unified Fixed SQL
  - LLM Fixer
  - Markdown / Text / JSON report
  - CLI and legacy CLI compatibility
- docs and handoff files for new conversation continuation
- tests

## Validation

The package was validated with:

```text
python -m pytest -q
24 passed
```

## Recommended Next Step

Start new conversation with `handoff/START_HERE_PROMPT.md`, then continue:

```text
Phase B: SQLPilotEngine API 收口
```
