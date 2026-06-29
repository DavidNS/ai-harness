# Decision 0001: Worker/Provider Boundary

Status: completed

## Context

Initial discovery reports were collected for lifecycle, phase execution,
investigation flow, state store, and worker provider.

The first refactor split large modules, but some extracted modules still behave
as adapter-mixins that delegate through the main orchestrator.

## Decision

Choose the worker invocation boundary as the first low-risk implementation
target.

`WorkerGateway` already owns provider invocation, job artifacts, debug
snapshots, control parsing, and phase validation. Remove the `WorkerExchange`
adapter-proxy behavior and make orchestrator forwarding explicit without
changing worker/provider behavior.

## Deferred Work

- state-store invariant extraction
- phase repair extraction
- investigation context extraction
