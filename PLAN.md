# PLAN — oloop

**Status:** current (2026-10-18). Earlier planning stages live in git history.

The order is dependency order, not necessarily chronological.

## Work packages

- [x] **AP1 — Project setup**
  Repos, `oloop-spec` as submodule in the clients, `.gitignore`, Apache-2.0 license in all four repos.

- [x] **AP2 — File format module (Python)**
  Package `oloop`: read/write frontmatter, atomic writing (temp file + `os.replace`), UUID assignment, project/task resolution (name → folder, ID → file), backup copy before writing (SPEC "Backup/recovery"). Validates against `schemas/*.schema.json` (this repo; the CLI keeps a copy in its package, a drift test fails if they diverge).

- [x] **AP3 — CLI commands**
  `project add/list/edit/find`, `task add/list/show/edit/close/reopen/image`, `comment add`, `--json` on read commands. Directly against AP2, no network layer. Released as `oloop` v0.1.0.

- [x] **AP4 — Android client** *(was not in the original plan)*
  `oloop-android`: plain Kotlin/JVM `core` (own re-implementation of the format) plus Jetpack Compose app. Passes the conformance fixtures as unit tests; runs on device.

- [ ] **AP5 — iOS/iPadOS client, then macOS** *(own approval per client)*
  Swift/SwiftUI, one multiplatform project; starts from `app-brief.md` (ready-to-use bundle: `oloop-ios/oloop-app-bundle.md`). Must pass `fixtures/`. Depends on: AP2 contract only.

- [ ] **AP6 — Windows client** *(provisional: .NET/WPF; revisit after the Apple clients)*
  Own re-implementation of the format; must pass `fixtures/`. Depends on: AP2 contract only.

- **Parked — MCP wrapper** (user decision 2026-10-16: not needed for now). Thin layer importing AP2 directly.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No lock on simultaneous writes (for example CLI + app at the same moment) | Last writer wins at task level, the losing write is lost | Reduced by atomic writing (no broken files), the race itself accepted on purpose (SPEC "Concurrent writes"): single-user tool, rarely truly simultaneous |
| Arbitrary file damage (bug, crash mid-write) | Loss of a single task file, not of the whole data set | Reduced by a backup copy before writing (SPEC "Backup/recovery") and by damage being structurally limited to one file |
