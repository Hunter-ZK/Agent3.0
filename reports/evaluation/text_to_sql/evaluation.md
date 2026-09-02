# Text-to-SQL Evaluation V2

## Configuration

- Cases: 1
- Repeat: 1
- Runs: 1

## Six-Layer Summary

| Layer | Rate |
| --- | ---: |
| Clarification | 100.0% |
| Planning | 0.0% |
| Schema Link | 100.0% |
| Generation | 100.0% |
| Gate | 100.0% |
| Semantic | 100.0% |
| Final | 0.0% |
| System Error | 0.0% |

## Stability

- Stable outcome cases: 1/1
- Stable PASS cases: 0/1
- Unstable cases: 0
- Stable PASS rate: 0.0%

## Redline

- GATE_FALSE_NEGATIVE runs: 0
- GATE_FALSE_NEGATIVE cases: 0
- Redline satisfied: True

## Failure Classification

| Failure Type | Count |
| --- | ---: |
| planning_error | 1 |

## Evidence Rule Hits

| Rule | Hits |
| --- | ---: |
| METRIC_TABLE | 0 |
| METRIC_AGGREGATION | 0 |
| METRIC_FIXED_FILTER | 0 |
| PARTITION_CONSTRAINT | 0 |

## Per-Case Stability

| Case | PASS | Runs | Stable Outcome | Stable PASS | Failure Types | Evidence Rules |
| --- | ---: | ---: | :---: | :---: | --- | --- |
| explicit_high_tech_month | 0 | 1 | True | False | planning_error | - |

## PASS with Evidence Advisories

None.
