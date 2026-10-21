# Conformance fixtures

Shared test data for every oloop implementation (Python CLI, and later Android, iOS, Windows).
An implementation conforms if it produces the expected results below.

- `valid/<case>/root/` is a data root. `valid/<case>/expected.json` holds the projects and tasks
  a reader must produce from it (`projects` and `tasks`, tasks sorted by `id`). Keys are the
  frontmatter fields plus `description` (Markdown body), and `projectName` on tasks. A missing
  `formatVersion` is read as 1.
- `invalid/<case>/root/` is a data root a reader must refuse. `invalid/<case>/expected_error.txt`
  holds a substring of the error message. Matching on the exact wording is not required, but
  an implementation must fail for the same reason.

Unknown frontmatter fields are valid and appear in `expected.json` like any other field
(`valid/unknown-fields`). A client that rewrites such a file must keep them. Every implementation
needs a round-trip test on `valid/unknown-fields` and `valid/due-date`: read, write, read again,
and the result equals `expected.json`.

The schemas in `../schemas/` are the authority for structure. These fixtures add the rules a
schema cannot express: the file name must equal the task `id`, and files with a newer
`formatVersion` must be refused.
