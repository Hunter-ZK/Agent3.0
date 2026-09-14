# Agent3.0 Full Capability Acceptance

This is the formal local acceptance path for production SQL capabilities.

## Non-negotiable rules

1. The SQL under test is selected by the human operator.
2. Formal acceptance must use a real LLM. Mock/Fake models are not accepted.
3. Human-in-the-Loop is mandatory.
4. `trusted_sql` means machine-trusted candidate; it is not final authorization.
5. A SQL artifact becomes `human_approved_sql` only when machine gates pass and the operator types the exact token `APPROVE`.
6. Human approval cannot override failed Program / Review / Critic / Metadata / Lineage gates.
7. Local validation artifacts are written under `validation_runs/`, which is ignored by Git.

## Environment

Create `.env` from `.env.example` and configure at least:

```env
DEEPSEEK_API_KEY=<your-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
AGENT3_USE_REAL_LLM=1
AGENT3_REQUIRE_HUMAN_APPROVAL=1
AGENT3_LLM_TIMEOUT_SECONDS=120
AGENT3_LLM_TEXT_TEMPERATURE=0
AGENT3_LLM_STRUCTURED_TEMPERATURE=0
```

## Existing-SQL full acceptance

```powershell
python examples/full_capability_acceptance.py `
  --sql "D:\path\case.sql" `
  --metadata-db "D:\path\agent_metadata.db" `
  --spec-json "D:\path\production_generate_spec.json" `
  --use-real-llm
```

The runner executes:

1. Program / Evidence
2. Production Explain with real LLM
3. Human approval of the explanation
4. Deterministic + LLM Review
5. Human approval of the review assessment
6. Production Fix when the chosen SQL has review issues
7. Re-review + Critic + machine gate
8. Human approval/rejection of the Fix candidate
9. Production Optimize with real LLM
10. Human approval/rejection of an optimization candidate
11. Production Generate when `--spec-json` is supplied
12. Metadata / Program / Lineage / Review machine gates for generated SQL
13. Human approval of the generated candidate
14. Final real-LLM Review of the active SQL
15. Final Human Approval

If any mandatory stage receives feedback, a blank response, a failed machine gate, or a rejection where continuation is unsafe, the run stops fail-closed.

## Production Generate spec

Use `examples/production_generate_spec.example.json` as the input shape and replace it with the business requirement, sources, target fields, partitions, parameters and constraints for the case being accepted.

A generated SQL candidate is not approvable unless `ProductionGenerateService.trusted_candidate` is true. With the default production policy this requires authoritative Metadata and successful Program / Review / Metadata / Lineage gates.

## Text-to-SQL HITL acceptance

Text-to-SQL has two Human-in-the-Loop concepts:

- clarification HITL: LangGraph interrupt -> human answer -> resume;
- final approval HITL: machine-trusted SQL -> exact human `APPROVE` -> human-approved SQL.

Current public loan-domain acceptance command:

```powershell
python examples/text_to_sql_demo.py `
  --question "统计贷款余额" `
  --use-real-llm `
  --require-human-approval
```

The demo may interrupt for clarification. After the SQL passes machine Trust and Semantic Validation, the final SQL is still withheld until the operator types `APPROVE`.

## Acceptance artifacts

The full runner writes a private local directory similar to:

```text
validation_runs/<run-id>/
  program_evidence.json
  explain.json
  review.json
  fix.json                 # when Fix is exercised
  fix_candidate.sql        # when produced
  optimize.json
  optimize_candidate.sql   # when produced
  generate_candidate.sql   # when --spec-json is supplied
  final_review.json
  human_decisions.json
  acceptance_report.json
  final_approved.sql       # only after final machine gate + exact APPROVE
```

`final_approved.sql` must not exist when final approval was not granted.

## Coverage interpretation

A single SQL case does not necessarily exercise every capability. In particular:

- if Review finds no issue, Fix is recorded as `not_exercised`;
- if Optimize returns advice only, optimization reasoning is exercised but no rewrite candidate exists;
- Production Generate is `not_exercised` unless `--spec-json` is supplied;
- execution/simulator validation needs table fixtures/data and remains a separate data-dependent gate.

For formal V1 sign-off, select cases that collectively exercise Explain, Review, Fix, Optimize, Generate, Text-to-SQL clarification/resume, and final approval.
