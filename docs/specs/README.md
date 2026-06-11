# Specs Index

`recursion-contract.md` is the canonical v1 contract. Other files in this
directory are supporting specs, implementation plans, or deferred design notes.

## Canonical

- `recursion-contract.md` - source of truth for the host contract, return
  envelope, budget rules, catalog semantics, determinism, and transport status.
- `budget-ledger.md` - ledger event and budget-accounting details used by the
  contract.
- `recursion-kinds-catalog.md` - catalog conventions and the boundary of
  allowed vs. excluded v1 kinds.
- `open-contract-issues.md` - unresolved contract ambiguities surfaced by the
  catalog stress fixture.
- `rlm-action-protocol.md` - structured JSON action protocol for `rlm_loop`.
- `rlm-loop-kind.md` - `rlm_loop` kind behavior.

## Implementation Plans

- `catalog-implementation-plan.md` - TDD plan and historical progress notes for
  catalog implementation. Some layout preferences in this plan predate the
  one-module-per-kind layout under `fleshwound/kinds/`.
- `rlm_plan.md` - plan and progress notes for the RLM loop.

## Long-Term Plans

- `larql-provider-integration-plan.md`
- `larql-provider-protocol.md`
- `spawned-mode-future.md`
- `spawned-worker-protocol.md`

Treat these as roadmap context, not active v1 requirements.
