# Known Issues

This file records intentionally deferred engineering debt.

It is not a backlog for speculative features.

An item may stay here only when all of the following are known:

1. the issue is real;
2. the current phase intentionally does not resolve it;
3. a future phase or owner is explicitly identified.

If no future consumer can be identified, the obsolete code or artifact
should be deleted instead of being recorded here.

---

## KI-001 — Semantic Asset / Physical Metadata Consistency

**Status:** DEFERRED  
**Owner:** Phase 1 — Fact Asset Alignment  
**Review Phase:** Phase 1.2

Approved semantic assets can currently drift from physical metadata
without a mandatory repository-level consistency gate.

Planned resolution:

- add `tests/test_semantic_assets_match_physical_metadata.py`;
- validate metric source tables;
- validate source columns;
- validate fixed-filter columns;
- validate default dimensions.

This issue must not be solved by duplicating structured business facts
into a second rule asset.

---

## KI-002 — Schema Linking Failure Is Not Yet Typed

**Status:** DEFERRED  
**Owner:** Phase 1 — Fact Asset Alignment  
**Review Phase:** Phase 1.3

`LinkedSchema` currently exposes unresolved information but does not yet
classify failures into stable categories.

Planned categories:

- `UNKNOWN_METRIC`
- `ASSET_COLUMN_MISSING`
- `TABLE_NOT_FOUND`
- `METADATA_ERROR`

Runtime handling will be implemented only after this contract is frozen.

---

## KI-003 — Evaluation Baseline Requires Asset-Aware Case Layers

**Status:** DEFERRED  
**Owner:** Phase 1 / Phase 3  
**Review Phase:** Phase 1.4, Phase 3

Golden cases do not yet fully distinguish product accuracy cases from
known asset gaps.

Planned resolution:

- `enabled=true` → Product Accuracy;
- `enabled=false + reason=asset_not_ready` → Asset Gap;
- Asset Gap count may decrease but must not increase silently.

---

## KI-004 — Metric Compilation Path Not Implemented

**Status:** DEFERRED  
**Owner:** Phase 4  
**Review Phase:** Phase 4

Semantic metrics currently participate in planning/linking/generation,
but there is no deterministic Metric Compiler that lowers approved metric
assets into structured SQL intent.

This is intentionally deferred until:

1. asset consistency is enforced;
2. typed linking failures exist;
3. evidence-grounded semantic rules are complete;
4. Evaluation V2 establishes a trustworthy baseline.