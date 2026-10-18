# oloop-spec

Specification of [oloop](https://github.com/greebo72/oloop-cli), a local cross-project tracker for todos, questions, decisions, features and bugs. The data lives as Markdown files with YAML frontmatter in a plain folder, so every client reads and writes the same files.

This repo is the contract between all oloop clients. It has no code to run apart from a small bundling script.

| Path | Content |
|---|---|
| `SPEC.md` | Purpose, non-goals, file format, native clients, open points |
| `schemas/` | JSON Schemas for `project.md` and task files. Authoritative for the structure |
| `fixtures/` | Valid and invalid sample data with expected results. Every client must pass them |
| `app-brief.md` | Platform-neutral brief for building a client app |
| `build_bundle.py` | Assembles brief, spec excerpts, schemas and fixtures into one upload file (`dist/oloop-app-bundle.md`) |
| `PLAN.md` | Work packages across all components |

## Components

- [oloop-cli](https://github.com/greebo72/oloop-cli): Python CLI and reference implementation. Released (v0.1.0), runs on macOS, Linux and Windows. Includes this repo as a submodule.
- [oloop-android](https://github.com/greebo72/oloop-android): Native Kotlin/Compose client for Android. Reads and writes the same files, runs the conformance fixtures as unit tests. See its README for status.
- [oloop-ios](https://github.com/greebo72/oloop-ios): Repo with the build brief only (`oloop-app-bundle.md`); the app has not been started. macOS is expected to follow in the same project.
- Windows client: planned (WPF, provisional).

## Changing the format

1. Change `schemas/`, `fixtures/` and `SPEC.md` together in one commit.
2. Raise `formatVersion` only for changes an old reader cannot handle. Adding an optional field does not.
3. In each client, update the submodule or copy and run its conformance tests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
