# Harness Ideas (Ryan Lopopolo Notes)

## Core Mental Models

### Code is free

-   Producing code is cheap.
-   Refactoring is cheap.
-   Migration is cheap.
-   Maintenance is increasingly automatable.
-   Human attention is the scarce resource.

### The repository is the prompt

The model is influenced by: - Repository structure - Documentation -
Skills - Tests - Lints - Review agents - Scripts - Naming - Architecture

The prompt is not a single text file; it is the repository itself.

### Everything is prompt injection

Prompt injection includes: - Documentation - Lint failures - Test
failures - Reviewer comments - Skills - CLI output - Architecture -
Repository structure

Every piece of text that reaches the model influences its behavior.

------------------------------------------------------------------------

# Learning Loop

``` text
Agent works
    ↓
Failure / Review feedback
    ↓
Extract invariant
    ↓
Document it
    ↓
Encode it as lint/test/reviewer
    ↓
Future agents stop making the mistake
```

The repository learns---not the model.

------------------------------------------------------------------------

# Harness Philosophy

The harness should **not** make decisions.

It should: - provide context, - provide tools, - provide constraints, -
provide feedback, - inject the right information at the right moment.

------------------------------------------------------------------------

# Repository Design

## Optimize for repository legibility

Goals: - Clear boundaries - Small modules - Explicit interfaces -
Consistent patterns - Minimal ambiguity

Benefits both humans and AI agents.

## Uniformity beats local optimization

Prefer: - one ORM - one async style - one logging pattern - one CI
style - one dependency injection approach

Consistency reduces cognitive load and model uncertainty.

## Locality of change

Ideal changes affect: - one subtree, - one package, - one domain.

Reduce hotspots.

------------------------------------------------------------------------

# Architecture

Large-scale refactoring is cheap **because it can be decomposed**.

Pattern:

``` text
Architecture change
    ↓
Many small PRs
    ↓
Independent merges
    ↓
Complete migration
```

Avoid giant PRs.

------------------------------------------------------------------------

# Guardrails

Convert recurring review comments into:

-   Documentation
-   Tests
-   Lints
-   Reviewer agents
-   Skills

Humans should not repeatedly review the same mistake.

------------------------------------------------------------------------

# Reflection

Continuously collect: - Agent sessions - PR comments - CI failures -
Human feedback

Then ask:

> How can the repository prevent this next time?

------------------------------------------------------------------------

# Skills

Maintain a **small number of high-quality skills**.

Improve existing skills before creating new ones.

------------------------------------------------------------------------

# Agent Principles

-   Don't put the agent in a box.
-   Give it context.
-   Give it tools.
-   Give it goals.
-   Let it reason.

------------------------------------------------------------------------

# CLI over GUI

Prefer: - structured text - concise output - machine-readable logs

Compress noise.

Show failures, not thousands of passing lines.

------------------------------------------------------------------------

# Interesting Ideas for My Harness

## Repository Improvement Agent

A permanent agent responsible for: - refactoring - documentation -
guardrails - lint rules - repository cleanup - architectural consistency

Not feature development.

## Garbage Collection Day

Regularly: - review recurring failures - identify missing context -
encode permanent fixes

## Repository as Knowledge Base

The repository should become the canonical engineering memory.

Everything valuable should eventually exist inside it.

------------------------------------------------------------------------

# Personal Takeaways

-   Build the repository, not just the harness.
-   Encode engineering judgment into executable constraints.
-   Move repeated human review into automation.
-   Treat repository evolution as prompt engineering.
-   Optimize for long-term leverage, not short-term implementation
    speed.