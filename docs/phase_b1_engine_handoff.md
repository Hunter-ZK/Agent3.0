# ADR: Agent3.0 Architecture Consolidation V1

Status: Accepted

## 1. Platform Position

Agent3.0 is a domain agent harness for
data warehouse development and data knowledge work.

## 2. Architecture Layers

1. Shared Runtime
2. Capability Workflow
3. Context Intelligence
4. Shared Data & Knowledge
5. Analysis / Review / Validation
6. Cross-cutting Infrastructure

## 3. Canonical Text-to-SQL Workflow

QueryAgentGraph is the only canonical
Text-to-SQL workflow.

TextToSQLService is a thin application facade.

No second Python workflow is allowed.

## 4. Context Contract

QueryContext is the request-scoped Context
contract for Text-to-SQL.

It contains:

- question snapshot
- semantic context
- business knowledge
- verified SQL
- session context

SemanticModel itself is not placed inside QueryContext.

## 5. Knowledge Ownership

Long-lived sources:

- Physical Metadata
- Semantic Model
- Business Knowledge
- Verified SQL
- Standards (deferred consumer)

Knowledge Source != Task Context.

## 6. Validation Ownership

SQL analysis and validation are shared
lower-layer capabilities.

They are not owned by any business Capability.

## 7. Runtime Ownership

Thread, Turn, Checkpoint, Retry and HITL
belong to Runtime.

Capability graphs own their nodes and routes.

## 8. Composition

app/text_to_sql_factory.py is the
Text-to-SQL Composition Root.

No IoC framework is introduced.

## 9. Deferred Work

Not part of Architecture Consolidation V1:

- SQL Review Capability
- Knowledge QA Capability
- Warehouse Modeling
- Naming Capability
- Lineage
- Skill Framework
- Intent Dispatcher
- Semantic YAML migration
- Certified Join
- Tool Framework

## 10. Change Rule

Shared contracts, persistence, runtime,
or capability boundaries require design review
before implementation.