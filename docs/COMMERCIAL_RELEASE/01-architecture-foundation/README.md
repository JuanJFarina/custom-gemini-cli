# Workload 1: Architecture Foundation

## Goal

Introduce the target package boundaries without changing runtime behavior.

## Scope

- Add the minimum `harle_domain`, `harle_services`, and `harle_infrastructure` package structure.
- Move or re-export the existing conversation and tool contracts through their correct layers.
- Keep temporary compatibility imports for `harle_agent`.
- Update package discovery and type-check configuration.
- Enforce the dependency direction defined in `.cursor/rules/hexagonal_architecture.mdc`.

## Not included

- Database migrations or schema changes
- Multi-user behavior
- New tools or feature behavior
- A full rewrite of `harle_agent`

## Done when

- Existing CLI and Telegram paths behave as before.
- New packages have no dependency cycles.
- Pre-commit checks pass.

This workload has no implementation dependency.
