# Product Boundary Evidence

This file is a lazy evidence index for completed product-refactor discovery.
Do not read it during startup. Use it only to understand completed product
boundary evidence.

| Boundary | Evidence |
| --- | --- |
| orchestrator lifecycle | Lifecycle should remain the thin shell for run entry, lock ownership, initialize/resume branching, execution-loop transitions, terminal status routing, and explicit context writes. |
| phase execution | Phase execution mixes generic repair/dispatch with SDD task/TDD adapter behavior; defer extraction because `_invoke_with_repair` is cross-cutting. |
| investigation flow | Extraction/publication context is explicit; keep it separate from discovery context and repository observation gathering. |
| state store | State mutation invariants are cohesive and should stay in `StateStore`; do not split decision, escalation, resume, or completion checks in this iteration. |
| worker provider | `WorkerGateway` owns provider invocation, job artifacts, control parsing, validation, and prompt shape. |
| phase repair | Generic contract repair is already centralized; defer broader extraction because only a low-value wrapper hoist is behavior-stable. |
| state record contract | Direct tests cover state record helper ID allocation and history publication without touching StateStore mutation behavior. |
| run progression | Runtime progression/terminalization is the strongest completed boundary; preserve resume gating, control-output exits, and snapshot/commit/cleanup ordering. |
| installation/bootstrap | Install/bootstrap tooling is separable and covered, but lower leverage than runtime orchestration for the current refactor objective. |
| resume loader coverage | ResumeContextLoader has direct coverage for pending strategy fallback and analysis-gate typed reload before runtime extraction. |
