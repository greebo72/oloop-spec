# oloop-spec

Specification of [oloop](https://github.com/greebo72/oloop-cli), a local cross-project tracker for todos, questions, decisions, features and bugs. The data lives as Markdown files with YAML frontmatter in a plain folder, so every client reads and writes the same files.

This repo is the contract between all oloop clients. It has no code to run apart from a small bundling script.

| Path | Content |
|---|---|
| `SPEC.md` | Purpose, non-goals, decisions, file format, client plan |
| `schemas/` | JSON Schemas for `project.md` and task files. Authoritative for the structure |
| `fixtures/` | Valid and invalid sample data with expected results. Every client must pass them |
| `app-brief.md` | Platform-neutral brief for building a client app |
| `build_bundle.py` | Assembles brief, spec excerpts, schemas and fixtures into one upload file (`dist/oloop-app-bundle.md`) |
| `PLAN.md` | Work packages across all components |
| `api-contract.yaml` | Obsolete HTTP contract, kept as history (German) |

## Components

- [oloop-cli](https://github.com/greebo72/oloop-cli): Python CLI and reference implementation. Includes this repo as a submodule.
- [oloop-ios](https://github.com/greebo72/oloop-ios): iOS and iPadOS client. macOS follows in the same project.
- Windows client: planned (WPF, provisional).

## Changing the format

1. Change `schemas/`, `fixtures/` and `SPEC.md` together in one commit.
2. Raise `formatVersion` only for changes an old reader cannot handle. Adding an optional field does not.
3. In each client, update the submodule or copy and run its conformance tests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
