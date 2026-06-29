# Harness Design Strategy Notes

Source: discussion about building an AI harness for coding, especially the plan to turn rough ideas into an SDD-style pipeline.

## What We Agreed On

- A messy repo should not be treated as a reason to stop. It is a reason to add guardrails and migrate by boundary.
- Do not try to clean the whole codebase first. Stabilize one path, then replace it incrementally.
- Transitional adapters are acceptable only if they stay thin. They are a bridge, not a second implementation of the same logic.
- The goal is to remove the adapter after the new flow proves itself.

## Practical Detection Strategy For "Mess"

Do not use a single AI "mess" flag.

Use a cheap signal stack instead:

- static analysis: lint, type errors, duplication, complexity, dead code
- architecture rules: forbidden imports, layer violations, cycle detection
- repo health: test failures, flaky tests, coverage on touched code
- history signals: churn, hotspot files, repeated edits

Let AI rank and explain those signals. Do not make AI invent the signal itself.

## Design Decision Approach

There is no magic algorithm for architecture decisions.

Use a repeatable loop:

1. extract constraints and non-goals
2. generate a few candidate designs
3. score them against a fixed rubric
4. write the decision down
5. implement one slice and verify it

Boundary discovery is useful, but it is not the same as choosing the right architecture. Discovery tells you where the seams are. Design decides what the seams should be.

## Configurability Stance

Recommended split:

- fixed core rules: dependency direction, recovery, auditability, testability, architecture invariants
- configurable policy: strictness, allowed layers, secrecy/redaction, explanation depth, risk tolerance

Default behavior should work for normal users without asking them to care about design principles.
Advanced users can get bounded profiles, but not freeform rewriting of the core architecture rules.

## Why This Fits The Repo

The repo already points in this direction:

- [Architecture Principles](../ARCHITECTURE.md)
- [Repo README](../README.md)
- [Executable architecture checks](../scripts/check_architecture.py)
- [Refactor archive](../refactor/archive/README.md)

The current structure already separates prompts, schemas, capabilities, tests, and refactor history. That is a good base for a staged SDD pipeline.

## Relevant External References

- Martin Fowler, Strangler Fig Application: https://martinfowler.com/bliki/StranglerFigApplication.html
- Microsoft, Strangler Fig pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig
- Code smell overview: https://en.wikipedia.org/wiki/Code_smell
- SonarQube rule quality paper: https://arxiv.org/abs/1907.00376

## Working Thesis

For this harness, the best default is:

- fixed architecture principles
- configurable policy around strictness and output style
- incremental replacement of legacy flows
- AI-assisted diagnosis, not AI-only judgment

That gives strong defaults for regular users and enough control for specialized cases without turning the core rules into a free-for-all.
