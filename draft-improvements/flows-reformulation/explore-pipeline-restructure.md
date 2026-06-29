# EXPLORE pipeline restructure

EXPLORE should become the first meaningful phase of the SDD flow:

```text
EXPLORE -> PURPOSE -> SPEC -> DESIGN -> TASKS -> IMPLEMENT -> TEST -> REVIEW -> ARCHIVE
```

The main goal of EXPLORE is not to propose implementations. The goal is to
understand the raw user request, decide how much exploration is needed, collect
evidence, validate that evidence, and produce the outcome bundle consumed by
PURPOSE.

EXPLORE should not route around PURPOSE. PURPOSE is the next phase and owns the
user-facing negotiation: presenting improvements, explaining limitations,
challenging bullshit premises, asking for clarifications, and deciding whether a
proposal can be written.

## Problem

The harness receives raw user input. That input can be structured, vague,
wrong, too broad, already implemented, impossible, or just a tiny typo.

The current explorer/analysis concepts contain useful pieces, but the order and
responsibility boundaries are unclear. Some pieces gather evidence. Some pieces
classify outcomes. Some pieces start to look like proposal or design work.

We need a clearer definition of what EXPLORE means.

## Proposed EXPLORE responsibilities

EXPLORE should answer these questions:

- What is the user asking for?
- How complex, ambiguous, risky, and novel is the request?
- What evidence is required before later SDD phases can make good decisions?
- What repository, external, and CI/workflow evidence supports or rejects the request?
- Which parts of the request classify as improvement, limitation, or bullshit?
- What does PURPOSE need in order to handle the next user-facing step?

EXPLORE should not answer:

- Which implementation approach should we choose?
- What exact architecture should we design?
- What tasks should be executed?
- What code should be changed?

Those belong to later phases.

## Proposed pipeline

```text
REQUEST_UNDERSTANDING
CLARIFICATION_GATE
EXPLORE_TRIAGE
EVIDENCE_PLAN
PARALLEL_EVIDENCE_COLLECTION
CI_EVIDENCE_BARRIER
EVIDENCE_NORMALIZATION
OUTCOME_BUNDLE_SYNTHESIS
EXPLORE_REVIEW
```

## 1. REQUEST_UNDERSTANDING

Normalize raw user input.

This phase should identify:

- user intent;
- target behavior or suspected problem;
- mentioned files, features, systems, APIs, or workflows;
- explicit constraints;
- unclear terms;
- request type: bug, feature, refactor, documentation, research, product idea,
  cleanup, typo, or unknown.

This phase should avoid deep repository analysis. It should only make the user
request understandable enough for triage.

Example output:

```json
{
  "intent": "refactor_or_flow_design",
  "summary": "User wants to redefine the SDD EXPLORE phase and its internal pipeline.",
  "mentioned_surfaces": ["explorer flow", "proposal", "git/gitlab analysis tools"],
  "explicit_constraints": ["Do not propose implementations during evidence gathering."],
  "unclear_parts": []
}
```

## 2. CLARIFICATION_GATE

Decide whether enough is known to build an evidence plan.

This is the only early pause in EXPLORE. It is for requests so vague that the
harness cannot decide what evidence to collect. EXPLORE should not ask the user
to choose approaches, approve tradeoffs, or resolve product direction here.
Those are PURPOSE responsibilities.

If the request is too vague, EXPLORE should still produce the normal outcome
bundle, but with `status` set to `needs_clarification` and no classified
entries. PURPOSE consumes that bundle and asks the user.

Example output:

```json
{
  "schema_version": 1,
  "kind": "explore_outcome_bundle",
  "status": "needs_clarification",
  "clarification_questions": [
    "Which part of the explorer flow should be reformulated first?"
  ],
  "entries": []
}
```

## 3. EXPLORE_TRIAGE

Decide how much exploration is needed.

Triage dimensions:

- `complexity`: typo, local change, multi-file, cross-cutting, architecture,
  migration;
- `ambiguity`: clear, partial, high, blocked by product decision;
- `novelty`: known repo pattern, uncertain feasibility, external research needed;
- `risk`: low, medium, high, critical;
- `evidence_depth`: light, standard, deep.

The point is to avoid running a full analysis pipeline for a typo while still
allowing deep analysis for broad, risky, or novel changes.

Example output:

```json
{
  "complexity": "architecture",
  "ambiguity": "partial",
  "novelty": "medium",
  "risk": "medium",
  "evidence_depth": "deep",
  "rationale": "The request changes phase boundaries and affects downstream SDD behavior."
}
```

## 4. EVIDENCE_PLAN

Create the evidence collection plan.

This phase decides which gatherers should run and what questions they must
answer. It should produce a plan, not conclusions.

Possible gatherers:

- `code`: repository files, symbols, tests, architecture docs, prompts, phase
  contracts;
- `git`: history, related commits, changed areas, blame when useful;
- `gitlab`: asynchronous branch pipeline evidence, including tests, code
  quality, coverage, static analysis, dependency checks, complexity reports,
  and pipeline artifacts;
- `web`: external docs, APIs, standards, libraries, feasibility research;
- `knowledge`: existing harness knowledge, previous improvement artifacts,
  limitations, decisions.

Example output:

```json
{
  "required_gatherers": ["code", "knowledge", "gitlab"],
  "optional_gatherers": ["web"],
  "questions": [
    "Where is EXPLORE currently defined?",
    "Which current explorer stages already collect evidence?",
    "Which stages currently classify outcomes or produce improvement artifacts?",
    "Which tests lock the current behavior?"
  ],
  "skip_reason": {
    "web": "No external API or standard is required unless novelty increases."
  }
}
```

## 5. PARALLEL_EVIDENCE_COLLECTION

Run independent evidence gatherers in parallel.

Each gatherer should return facts and source references. Gatherers should not
return implementation proposals.

Examples:

- Code gatherer finds relevant files, symbols, phase definitions, prompts, and
  tests.
- GitLab pipeline starts at run initialization after the harness creates the
  branch and pushes it. EXPLORE should not wait for it during request
  understanding, triage, evidence planning, or local/web evidence collection.
- Web gatherer checks external feasibility when the request depends on external
  tools, APIs, laws, standards, libraries, or current behavior.
- Knowledge gatherer checks existing improvement, limitation, and decision
  artifacts to avoid duplicate work.

Gatherers should be allowed to report blockers:

- repository evidence unavailable;
- CI failed to run;
- external source unavailable;
- request requires user product direction;
- evidence contradicts the user claim.

## 6. CI_EVIDENCE_BARRIER

Join asynchronous GitLab evidence before final synthesis when the evidence plan
requires it.

The branch pipeline should start near the beginning of the run, outside the
blocking part of EXPLORE. Early EXPLORE phases can proceed using request,
repository, knowledge, git, and web evidence while GitLab runs in the
background.

The evidence plan decides whether GitLab evidence is required, optional, or not
needed:

- `required`: wait at the CI barrier until the pipeline finishes or a configured
  timeout/budget is reached;
- `optional`: consume GitLab evidence if it is ready, but do not block outcome
  bundle synthesis;
- `not_needed`: ignore GitLab for this run.

Required GitLab evidence should be reserved for requests where CI facts can
change the classification or materially affect PURPOSE. Examples include
requests about test health, code quality, coupling, dependency risk, coverage,
large refactors, or branch-specific pipeline behavior.

If required GitLab evidence cannot be collected because the pipeline did not
start, credentials are missing, artifacts are unavailable, or the run times out,
EXPLORE should produce `status=problem_gathering_info`. If GitLab ran
successfully and found no support for the requested capability, the result is not
`problem_gathering_info`; it should be represented as evidence for a
`limitation` or `bullshit` classification.

## 7. EVIDENCE_NORMALIZATION

Convert raw gatherer output into a common evidence model.

Raw tool output should not go directly into PURPOSE, SPEC, or DESIGN. It should
first become structured claims with source references.

Example evidence item:

```json
{
  "id": "E1",
  "claim": "The current staged explorer has a decision phase after discovery.",
  "status": "supported",
  "confidence": "high",
  "sources": [
    {
      "type": "file",
      "path": "harness/ai_harness/orchestrator/explorer_phase_service.py",
      "symbol": "ExplorerPhaseService.decision"
    }
  ]
}
```

Suggested statuses:

- `supported`;
- `contradicted`;
- `partially_supported`;
- `unresolved`;
- `not_applicable`;
- `blocked`.

## 8. OUTCOME_BUNDLE_SYNTHESIS

Build the single artifact handed from EXPLORE to PURPOSE.

Suggested artifact:

```text
explore/outcome_bundle.json
```

This bundle is both the evidence synthesis and the outcome classification. A
separate `evidence.json` can be introduced later if the bundle becomes too large,
but the first target should be one clear handoff artifact.

The bundle has two different concepts:

- `status`: whether PURPOSE can act on the bundle, needs to ask for
  clarification, or must report that EXPLORE could not gather required
  evidence because an evidence source failed.
- `entries[].classification`: the domain classification for each part of the
  request.

Allowed bundle statuses:

- `ready_for_purpose`: entries are classified and PURPOSE can continue;
- `needs_clarification`: the request is too vague to build an evidence plan;
- `problem_gathering_info`: EXPLORE knew what evidence was required, but one or
  more planned evidence sources could not be queried or returned unusable data.

`problem_gathering_info` is operational, not semantic. It is for cases such as
no internet, unavailable GitLab credentials, missing pipeline artifacts,
incomplete repository checkout, or a gatherer timeout. If EXPLORE searched the
planned sources successfully and found no supporting evidence, that is not
`problem_gathering_info`; it should become a `limitation` entry with the searched
sources recorded as evidence.

Allowed entry classifications:

- `improvement`: evidence supports a real change worth discussing in PURPOSE;
- `limitation`: coherent request, but blocked by product, repository, technical,
  execution, permission, or environment constraints;
- `bullshit`: premise should be rejected because it is absurd, contradictory,
  evidence-contradicted, or violates core repo/product principles.

Examples:

- `problem_gathering_info`: live GitLab pipeline evidence is required, but the
  run has no network or GitLab credentials.
- `limitation`: the planned repository and web searches completed, but found no
  evidence that the requested capability exists or is feasible under current
  constraints.
- `bullshit`: the request asks implementation workers to mutate controller state
  directly, contradicting the controller-owned validation and persistence
  principle.

Possible shape:

```json
{
  "schema_version": 1,
  "kind": "explore_outcome_bundle",
  "status": "ready_for_purpose",
  "normalized_request": {
    "summary": "User wants EXPLORE to produce the artifact consumed by PURPOSE."
  },
  "triage": {
    "complexity": "architecture",
    "ambiguity": "partial",
    "risk": "medium",
    "evidence_depth": "deep"
  },
  "evidence": [
    {
      "id": "E1",
      "claim": "The current explorer flow has separate discovery, decision, artifact, and review stages.",
      "status": "supported",
      "sources": [
        {"type": "file", "path": "harness/ai_harness/orchestrator/explorer_phase_service.py"}
      ]
    }
  ],
  "entries": [
    {
      "id": "explore-purpose-handoff",
      "classification": "improvement",
      "title": "Make EXPLORE produce a PURPOSE-ready outcome bundle",
      "problem": "The current model blurs evidence synthesis, outcome classification, and proposal routing.",
      "evidence_refs": ["E1"],
      "constraints": [
        "EXPLORE must not propose implementation approaches.",
        "PURPOSE must own user-facing decisions and proposal framing."
      ],
      "unknowns": []
    }
  ]
}
```

Important boundary:

```text
EXPLORE classifies evidence into a bundle.
PURPOSE decides the user-facing next step from that bundle.
PURPOSE proposes approaches only for improvement entries.
```

## 9. EXPLORE_REVIEW

Review the evidence and outcome bundle before the flow advances.

The review should check:

- every important claim has evidence or an explicit unresolved reason;
- repository-answerable unknowns were not left unresolved;
- the triage depth matches the request complexity and risk;
- simple requests were not over-analyzed;
- complex or risky requests were not under-analyzed;
- entry classification follows from the evidence;
- the bundle does not contain implementation design disguised as exploration;
- PURPOSE has enough information to handle the next user-facing step.

Possible review outcomes:

- approve the bundle for PURPOSE;
- rerun one or more gatherers;
- rerun triage with corrected depth;
- mark the bundle as `needs_clarification` when no safe evidence plan is
  possible;
- mark the bundle as `problem_gathering_info` when required evidence sources
  failed operationally.

## PURPOSE handoff

EXPLORE always hands `explore/outcome_bundle.json` to PURPOSE.

PURPOSE owns the user-facing behavior:

```text
status=needs_clarification -> PURPOSE asks the clarification question
status=problem_gathering_info -> PURPOSE explains the failed evidence source or triggers an EXPLORE retry
classification=improvement -> PURPOSE proposes approaches, scope, exclusions, and acceptance outline
classification=limitation  -> PURPOSE explains the blocker and asks whether to stop or reframe
classification=bullshit    -> PURPOSE challenges the premise and allows counter-argument or rephrase
mixed entries              -> PURPOSE decides sequencing, splitting, or priority questions
```

User counter-arguments should be verified by returning to EXPLORE evidence
collection. PURPOSE should not validate factual claims by itself.

## Relationship with current repo concepts

Current useful pieces:

- `explorer_intake` resembles `REQUEST_UNDERSTANDING`;
- `explorer_discovery` contains evidence collection ideas, but also includes
  candidate directions that belong later;
- `explorer_decision` mixes outcome classification with routing decisions and
  should be narrowed or absorbed into outcome bundle synthesis;
- `explorer_artifact` currently creates improvement/limitation/existing
  artifacts, which maps to `OUTCOME_BUNDLE_SYNTHESIS`;
- `explorer_review` maps well to `EXPLORE_REVIEW`;
- `explorer_distill` may still be useful after classification, but should not
  hide evidence or turn exploration into implementation planning.

Suggested refactor direction:

- make `explore/outcome_bundle.json` the final EXPLORE artifact and the only
  required PURPOSE input;
- keep entry classifications minimal at first: `improvement`, `limitation`, and
  `bullshit`;
- keep readiness and operational collection failures at the bundle level with
  `status`, not as entry classifications;
- move candidate directions and implementation alternatives out of EXPLORE and
  into PURPOSE;
- let PURPOSE decide user-facing questions, stopping behavior, reframing, and
  proposal framing from the bundle.
