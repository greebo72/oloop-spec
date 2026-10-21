# SPEC — oloop (local cross-project tracker)

**Status:** current (2026-10-18). Superseded: the entire pre-file-format planning; its outcome (Markdown + YAML frontmatter files, no service, no network layer) is simply assumed below. Past versions live in git history.

oloop keeps open items — todos, questions, decisions, features and bugs — as plain Markdown files with YAML frontmatter in one data folder, one folder per project. Clients: the Python CLI (reference implementation), the Android app; iOS/iPadOS, macOS and Windows are planned. This repo is the contract between them: schemas, fixtures, and the rules below.

## Purpose

The user works on many projects in parallel (different directories, some inactive for weeks). Open todos, unanswered questions, decisions made and key features get lost between sessions and projects, and there is no central overview of what is open where. oloop is the local tool for that: Markdown files with YAML frontmatter as storage (managed by the tool, never edited by hand), a Python module used directly by the CLI, and native clients reading and writing the same files. There is no server, no account and no network access.

## Non-goals

- **Multi-user/auth** — single-user tool, no login, no role model.
- **Multiple devices** — no sync protection, no cross-device locking, no conflict-copy detection. Keeping the data folder in sync across devices is the folder's own job (Syncthing, cloud drive, …), not the tool's.
- **Network/service layer** — deliberately none. Every client accesses the files directly and re-implements the documented format.
- **Direct editing of the files by the user** — explicit requirement. The Markdown files are an implementation detail of the tool, not a user interface.

## Backup/recovery

Many small files instead of one binary file are more robust by nature: one damaged task does not kill the whole data set. **In scope for V1:** before every write, the writer copies the affected file to `.backup/<filename>.bak` (one generation, no rotation scheme). This is cheap protection against the remaining failure cases (a bug in the write path, a crash mid-write) that atomic rename writes leave open in theory. More (versioning, several generations) is not part of this approval.

## File format

```
<data-root>/                       -- path configurable (CLI config/ENV, no hardcoding)
  <project-slug>/
    project.md                     -- frontmatter: formatVersion, id (UUID), name, createdAt,
                                       optional referencePath, referenceHost
    tasks/
      <task-id>.md                 -- file name = UUID, stable over the task's lifetime
                                       (changing the title does NOT rename the file, so
                                       references and comments stay stable)
    images/
      <task-id>.<ext>              -- optional image per task, next to the task file
```

Frontmatter per task (YAML header, `python-frontmatter` compatible):

```yaml
formatVersion: 1
id: <uuid>
projectId: <uuid>
type: todo|question|decision|feature|bug
title: "..."
status: open|closed
imagePath: null | "images/<task-id>.<ext>"
dueDate: 2026-11-01                  # optional, may be absent or null
createdAt: 2026-10-16T12:00:00Z
createdBy: user
updatedAt: 2026-10-16T12:00:00Z
updatedBy: user
labels: [backend, urgent]
comments:
  - body: "..."
    createdAt: 2026-10-16T12:05:00Z
```

Markdown body = `description`. **Authoritative for the exact structure:** `schemas/project.schema.json` and `schemas/task.schema.json` (in this repo); the schema files win on conflict. The Python CLI (`oloop-cli`) includes this repo as a Git submodule, carries a copy of the schemas so its wheel is self-contained, and a test fails if the copy drifts.

**Conformance fixtures:** `fixtures/` holds shared test data (valid data roots with the expected result, invalid ones with the expected error). Every implementation must pass them. Every implementation also needs a round-trip test: read a valid fixture, write it back, read it again, and get the same result, including `dueDate` and unknown fields (`valid/due-date`, `valid/unknown-fields`). See `fixtures/README.md`.

**`formatVersion`:** integer in the frontmatter of every file, currently `1`. Writers always set it. Readers treat a missing value as 1 and must refuse a value higher than the one they know, so an old client never rewrites data it does not understand. It increases only for changes an old reader cannot handle; adding an optional field does not.

**Unknown fields:** readers accept frontmatter fields they do not know (in project and task files and in comment entries) and must not drop them. When a client rewrites a file, it writes the unknown fields back unchanged, so an older client never erases a field a newer one added. They are not validated and do not count as an error. This is what lets optional fields such as `dueDate` be added without a `formatVersion` bump.

**Relative `imagePath`:** images are plain files next to the task, not embedded data.

**Task image (add, replace, remove):** a task has at most one image, stored as `images/<task-id>.<ext>` in the project folder. `<ext>` is the lowercase extension of the chosen source file and one of `png`, `jpg`, `jpeg`, `gif`, `webp`; a client refuses other files with a clear message. The source file stays untouched, the client works on a copy.
- *Add / replace:* copy the file to a temporary file, then replace the target. After that write the task with `imagePath` set, and update `updatedAt` and `updatedBy`. If writing the task fails, remove the new image file again unless it replaced an existing one. If a replacement has a different extension than the old image, the old file is removed once the task is written, so no orphan stays behind.
- *Remove:* write the task with `imagePath: null` and update `updatedAt` and `updatedBy`, then delete the image file. If deleting the file fails, the link stays removed and the client reports the error.
- Image files are not backed up to `.backup/`, only task and project files are.
- Readers ignore files in `images/` that no `imagePath` points to. An `imagePath` whose file is missing is not an error: the client shows that the image is missing.

**`createdBy`/`updatedBy`/`labels`:** the actor is a free-text string (source: parameter, else `$OLOOP_ACTOR`, else OS user name). `updatedBy` is set together with `updatedAt` on every change, `createdBy` never. `labels` is a list of unique strings, replaceable via edit.

**Comparing labels:** labels are stored exactly as written, but every comparison between labels (filtering, searching, building a list of the labels in use) ignores case: `Bug` and `bug` are the same label. The comparison does not depend on the locale or the platform (Unicode case folding, for example `casefold()` in Python or `StringComparison.OrdinalIgnoreCase` in .NET), so every client gives the same result. When a filter takes several labels, a task matches if it carries at least one of them (OR). A list of the labels in use shows each label once and counts its tasks across all spellings; which spelling it displays is up to the client. This rule changes nothing in the files: writers do not rewrite labels, and whether `Bug` and `bug` on the same task count as a duplicate when writing is not decided here.

**`dueDate` (task, optional):** the calendar date by which a task should be done, written as `YYYY-MM-DD`. It is a plain date, not a timestamp: no time and no time zone, so it means the same day on every machine. Absent and `null` both mean "no due date". Writers omit the field when there is none. It does not depend on `status`, so a closed task keeps its `dueDate`. Setting, changing or clearing it counts as an edit: `updatedAt` and `updatedBy` are updated. Unlike all other timestamps it is not UTC, see the exception in "Timestamps".

**`referencePath`/`referenceHost` (project, optional):** working directory (for example a repo) a project belongs to, and the machine name it applies to. `oloop project find` maps a directory to a project (longest matching path wins, host must match). If a path is given without a host, the current machine name is stored.

**One `status` field, no enum per type:** the label in the presentation layer varies per type (todo → "Done", question → "Answered", decision → "Decided", feature → "Implemented", bug → "Fixed"). The data model stays `open`/`closed`.

**`updatedAt` is a required field, not an extra:** the tool's central purpose is to see what happened last after one or two quiet weeks. CLI and clients filter and sort by it.

**No delete, anywhere.** "Mark as finished instead of delete is the way." Task, comment and project are append-only. `close`/`reopen` (a status flip in the frontmatter) is the only completion mechanism, and no task, comment or project file ever disappears. The one exception is the image of a task: it can be removed or replaced, see "Task image".

**Edit allowed, but limited.** `title`/`description`/`dueDate` of a task can be corrected afterwards (overwrites the frontmatter field or the Markdown body, `updatedAt` is updated, the file name stays stable). Project name and task type are NOT editable in V1.

**ID scheme:** UUID4 per entity (no auto-increment without a DB). File name = ID.

**Timestamps:** UTC, ISO 8601 with `Z`. Localization happens on the display side (CLI/UI), not in the file format. The one exception is `dueDate`, a plain `YYYY-MM-DD` calendar date without time zone. Relevant for the stale-days filter in the CLI.

**Concurrent writes:** there is no locking, last writer wins. Atomic writing (temp file + replace) prevents half-written files; a real race between two simultaneous writes to the same task is an accepted residual risk for a single-user tool. Clients re-read before writing and surface a changed `updatedAt` as a conflict instead of overwriting silently.

## Native clients

Each client re-implements the file format (no shared code between Kotlin, Swift, C# and Python). All of them must pass `fixtures/`, which is the common yardstick. `app-brief.md` is the platform-neutral brief for building one.

- **Android:** shipped (Kotlin/Jetpack Compose, `oloop-android`), running on device; the fixtures run as unit tests there.
- **iOS / iPadOS, then macOS:** one Swift/SwiftUI multiplatform project (`oloop-ios` holds the build brief; not started).
- **Windows:** planned (.NET with WPF, provisional).

Look and structure: project list, task list with the project name in a header, grouping by creation date, modification date, type or status, and an editable task detail, as in the app brief. "Silent since" (follows from `updatedAt`) is a first-class view. Later additions that sit on top of a finished app: a menu-bar/tray item with a global shortcut for quick capture, widgets or jump lists.

## Open points

- **Windows toolkit** is provisional (WPF); revisit once the Apple clients exist.
- **MCP wrapper:** not needed for now (user decision); it would import the CLI's Python module and can be added later for clients without a shell.
