# SERVER — optional server backend for oloop

**Status:** DRAFT (2026-11-14). Not implemented anywhere yet. Nothing here changes the folder format in `SPEC.md`; the folder backend stays the default and stays complete without a server.

A client can keep its data on an oloop server instead of in a data folder. The server stores only encrypted data: all encryption and decryption happens in the client. This document is the contract between the clients that support it (the desktop client, the CLI) and the server (`oloop-server`, a separate repo).

## Scope

- **Optional.** A client may ignore this document. The non-goals of `SPEC.md` (no server, no account, no network) describe the folder backend and still hold for it.
- **Same data model.** Projects and tasks are exactly those of `SPEC.md`: same fields, `formatVersion`, unknown-field preservation, no delete, edit limits, label rules, timestamps. Only the place where they are stored differs.
- **One person, several devices, and agents.** V1 serves one person. That person can let **agents** work in chosen projects: the CLI run by an LLM on the person's behalf, see `AGENTS.md`. The protocol and the key structure already allow other people as members of a project; the server switches that on later without a change of format (see Open points).
- **Online only** in V1. There is no offline queue and no local copy that is written to.

## Deployment assumptions

The server runs behind a reverse proxy that is operated separately and is not part of this contract.

- The proxy ends TLS. The server itself speaks plain HTTP on an internal address.
- The server trusts `X-Forwarded-For` and `X-Forwarded-Proto` only from proxy addresses it is configured with.
- The proxy allows request bodies at least as large as the limits below.
- A client accepts only `https://` server addresses. `http://` is accepted for loopback addresses (`localhost`, `127.0.0.1`, `::1`) only.

## Principals

A **principal** is whoever acts on the server. There are two kinds:

| Kind | Authenticates with | Holds |
|---|---|---|
| `user` | user name and password, then short-lived tokens | a key pair protected by a passphrase |
| `agent` | a long-lived, revocable token | its own key pair, unprotected, in a credentials file |

An agent belongs to exactly one user, who creates it. A user sees all projects they own. An agent sees only the projects that were granted to it, with a role: `owner` (users only), `write` or `read`. The server enforces roles; they are not a cryptographic protection (see Threat model). Agents are specified in `AGENTS.md`.

## What is stored where

The unit of storage is a **document**: one project or one task, kept as the **plaintext payload** below, encrypted.

**Plaintext payload.** The exact text the folder backend would write for that entity: the contents of `project.md` or of `tasks/<id>.md`, UTF-8. A reader of a payload applies every rule of `SPEC.md` to it, including the check of `formatVersion` and the preservation of unknown fields.

**Visible to the server** (metadata the protocol needs):

| Field | Meaning |
|---|---|
| `id`, `kind`, `projectId` | UUID of the document, `project` or `task`, and for a task the UUID of its project |
| `rev` | integer revision, starts at 1, see Concurrency |
| `keyVersion` | which key of the project encrypted the document |
| `blobRef` | for a task, the id of its image blob or `null` |
| `writtenBy` | the principal that wrote the revision. Set by the server, a client cannot choose it |
| principals, roles, public keys | who exists, who is a member of which project, with which role |
| size, server timestamps | bookkeeping |

**Not visible to the server:** title, description, labels, comments, type, status, due date, actor names, project names, reference paths, image contents, and the `updatedAt` inside the payload. The server also sees that documents exist, how big they are, when they change and who may read them; hiding that is a non-goal.

Because the server cannot read a payload, everything that depends on content is done by the client after loading: search, filters, grouping, label lists, the check that a project name is unique. Two clients that create a project of the same name at the same moment can therefore produce duplicates; clients show both.

## Encryption

All cryptography is libsodium, so every client uses the same primitives through a binding (for example Sodium.Core for .NET, PyNaCl for Python).

| Purpose | Primitive (libsodium) |
|---|---|
| Passphrase to key | `crypto_pwhash`, Argon2id (`ALG_ARGON2ID13`), 32 byte output |
| Encrypting data | `crypto_aead_xchacha20poly1305_ietf` (192 bit random nonce) |
| Key pair | `crypto_box_keypair` (X25519) |
| Handing a key to a principal | `crypto_box_easy` (authenticated, see below) |
| Hash of a blob | SHA-256 |

XChaCha20-Poly1305 is used and not AES-GCM because it is available on every machine and because its nonce is long enough to be chosen at random for every encryption.

### Key hierarchy

```
passphrase ──Argon2id──▶ passphraseKey ──encrypts──▶ user secret key  (X25519)
recovery code ───────────────────────────encrypts──▶ user secret key  (second copy)

project key (random, 32 bytes, per project and keyVersion)
    └─ handed to each member through crypto_box, from the granting principal to the member
         ├─ encrypts the project document and all task documents of the project
         └─ encrypts the image blobs of the tasks of the project
```

- **User key pair.** Created by the first client during setup. The public key is stored on the server in clear text. The secret key is stored on the server **only encrypted**, twice: with the passphrase key and with the recovery code.
- **Passphrase.** Never sent to the server, and not the login password; a client tells the user to choose another one. It enters Argon2id as the **UTF-8 bytes of the text exactly as it was typed or pasted, without any normalization**: no two implementations can be relied on to normalize alike, and some cannot at all (a .NET program in invariant globalization mode leaves non-ASCII text unchanged). A character with more than one spelling therefore gives another key: `ü` as one character and `u` followed by a combining diaeresis are two different passphrases. Every common keyboard gives the same spelling on every device; the recovery code is the way back when it does not. Text that is not valid Unicode (a lone surrogate) is refused. The vectors pin this down (`kdf.encoding`).
- **Recovery code.** 32 random bytes, used directly as the key of the second copy, shown once during setup as base32 (RFC 4648 alphabet, no padding) in groups of four letters joined by `-`: 52 letters, 13 groups, the last letter with 4 unused bits. A client reads a typed code without regard to case, spaces and dashes, and refuses one that does not have exactly 52 letters of the alphabet or whose unused bits are not zero (otherwise two spellings would stand for one code). The vectors pin this down (`recoveryCode`). Without the passphrase and without the code the data cannot be recovered; the client must say so before it finishes the setup.
- **Key bundle**, stored by the server: `{ v, kdf: "argon2id", salt, m, t, publicKey, wrappedSecretKey, recoveryWrappedSecretKey }`. `m` is the memory in bytes, `t` the number of passes (libsodium has no separate parallelism). `salt` is 16 bytes. The two wrapped keys are envelopes (below) with the user id as the identity. After unlocking, a client checks that the public key belonging to the secret key equals `publicKey`.
- **KDF cost.** Default for new bundles: `m` = 64 MiB, `t` = 3. A client refuses to unlock a bundle with `m` below 19 MiB or `t` below 2, so a server cannot weaken the passphrase protection by changing the parameters.
- **Changing the passphrase** encrypts the same secret key anew. No document and no project key changes.
- **Project key.** 32 random bytes, generated by the client that creates the project. A project has a `keyVersion` (1 at first). Every member has a copy, kept by the server, in the form below.

### Handing a project key to a principal

`wrapped` = `nonce` (24 bytes) followed by `crypto_box_easy(message, nonce, recipientPublicKey, senderSecretKey)` with

```
message = projectKey (32 bytes) | projectId (16 bytes, the UUID) | keyVersion (4 bytes, big endian)
```

The recipient opens it with its secret key and the **sender's public key**, and then checks that `projectId` and `keyVersion` in the message are the ones it asked for. The entry names the sender (`grantedBy`).

The point of `crypto_box` over a sealed box: a sealed box can be made by anyone who knows the recipient's public key, and the server does. The server could then hand the recipient a key that it knows itself. With an authenticated box only the holder of the sender's secret key can make it. A client therefore never takes the sender's public key from the server's answer on its own authority:

- for a key it granted itself, the sender is itself;
- for a key granted by another principal, it uses the public key it **pinned** when it first accepted a key from that principal, and refuses a different one;
- an agent gets the public key of its user in its credentials file, from the user's own client. No one has to compare anything.

A key pair is the identity: the pin is checked against the public key stored in the key bundle or in the credentials, never against a name.

### Envelope

Binary, used for documents, blobs and the wrapped secret keys:

```
byte 0       v      envelope version, 1
byte 1       alg    1 = XChaCha20-Poly1305 (IETF)
bytes 2..25  nonce  24 random bytes
bytes 26..   ciphertext followed by the 16-byte tag
```

**Associated data** (authenticated, not stored): the two bytes `v` and `alg`, followed by each field of the list below as UTF-8 text, **each preceded by one `0x00` byte**. UUIDs are lowercase text; numbers are decimal text.

- document: `"doc"`, `kind`, `id`, `keyVersion`, `rev`
- blob: `"blob"`, `blobId`, `taskId`, `keyVersion`
- wrapped secret key: `"key"`, user id

This binds a ciphertext to its item, its key and its revision: the server cannot hand out one document as another, or an old revision as a newer one, without the tag check failing.

A client that meets a `v` or `alg` it does not know stops and reports it. It never writes data it could not read.

### Limits of the protection

A malicious server can withhold or delete data, and it can answer with an older state of a whole document that was consistent at the time. A client keeps the highest `rev` it has seen per document on this device and warns when the server shows a lower one. A server cannot read data, and cannot change it without detection. Other limits are listed under Threat model.

## Authentication

- Users sign in with a user name and password. The server stores only an Argon2id hash of the password. Accounts are created by the operator (`oloop-server create-user`); there is no public registration endpoint.
- `POST /v1/auth/login` returns a short-lived access token (15 minutes) and a refresh token. Every request except `GET /healthz` carries `Authorization: Bearer <token>`.
- Refresh tokens belong to a device, rotate on every use, and a refresh token that is used twice revokes its device. `POST /v1/auth/logout` revokes the device.
- An **agent token** is an opaque random string that is used directly as the bearer token. It expires, can be renewed under rules, and is revoked at once by its user; see `AGENTS.md`.
- The server limits failed logins and answers `429` with `Retry-After`.
- A client keeps tokens, and the secret key if the user chose "remember on this device", in the operating system's secret store, never in the settings file. The CLI follows `AGENTS.md`.

## API v1

JSON (UTF-8) unless noted. Binary values inside JSON are base64url without padding. Times are UTC, ISO 8601 with `Z`. The version is in the path; an incompatible change is `/v2`.

An error is `{ "error": { "code": "...", "message": "..." } }` with a status:

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | malformed body, unknown `kind`, wrong id |
| 401 | `unauthorized` | missing, expired or revoked token |
| 403 | `forbidden` | the role does not allow it (for example an agent creating a project) |
| 404 | `not_found` | also for a project the caller is not a member of, so its existence is not revealed |
| 409 | `conflict` | `If-Match` does not match, see Concurrency |
| 413 | `too_large` | over a limit below |
| 429 | `rate_limited` | |

**Auth**

```
POST /v1/auth/login      { username, password, deviceName }
                         → { accessToken, expiresIn, refreshToken, userId }
POST /v1/auth/refresh    { refreshToken } → { accessToken, expiresIn, refreshToken, userId }
POST /v1/auth/logout
GET  /healthz            → 200, no data, no authentication
```

`userId` is the UUID of the user (lowercase, with dashes). The two calls that hand out tokens return it, so that a client has it from the first moment. It needs it for the associated data of its key bundle (`"key"`, user id) before there is a bundle to ask for, to see which key hand-overs it made itself (`grantedBy`), and to show which revisions it wrote (`writtenBy`). It is not the user name, which a person types and which the server compares without regard to case.

**Key bundle** (users)

```
GET /v1/keys             → { keyRev, bundle }       404 until set up
PUT /v1/keys             { bundle }
                         If-None-Match: *           first setup
                         If-Match: "<keyRev>"       passphrase change
                         → { keyRev }
```

The server cannot judge the encryption of a bundle; it checks the form and refuses a bundle that is wrong with `400`:

- `v` is 1 and `kdf` is `"argon2id"`; no other field is accepted.
- `salt` is 16 bytes and `publicKey` 32 bytes. `wrappedSecretKey` and `recoveryWrappedSecretKey` are envelopes of 74 bytes (header, nonce, the 32 byte secret key and the tag) with `v` 1 and `alg` 1.
- Binary values are base64url without padding, in the shortest form.
- `m` is at least 19 MiB and `t` at least 2 (the minimum a client accepts), and both are at most 2^32 − 1, what libsodium takes.

Exactly one of `If-None-Match: *` and `If-Match` is required, otherwise `400`. A failed precondition is `409 conflict`; an `If-Match` for a bundle that does not exist is `404`. An update must keep `publicKey`: the key pair is the identity of the user, and other principals hold keys sealed to it. Only the encryption of the secret key may change, as in a change of the passphrase. `keyRev` starts at 1 and is also sent as `ETag`.

**Agents:** the endpoints for creating, renewing and revoking agents are in `AGENTS.md`.

**Projects and members**

```
GET /v1/projects         → [{ id, role, keys: [{ keyVersion, grantedBy, wrapped }] }]
                           the projects the caller is a member of, with the caller's own keys
GET /v1/projects/{id}/members                       (owner)
                         → [{ principalId, kind, name, role, publicKey }]
PUT /v1/projects/{id}/members/{principalId}         (owner)
                         { role, keys: [{ keyVersion, wrapped }] }
POST /v1/projects/{id}/revoke                       (owner)
                         { principalId, newKey?: { keyVersion,
                                                   members: [{ principalId, wrapped }] } }
```

The first `PUT` of the project document makes the caller its owner (see Documents). In V1 the server accepts only agents as further members. Revoking a member with `newKey` raises the `keyVersion` of the project: `newKey` must carry a `wrapped` for every remaining member, or the server answers `400`. Members keep the older versions of the key they already have; those stay in `keys`.

**Documents**

```
GET /v1/head             → { cursor }
GET /v1/documents?cursor=<c>&limit=<n>
                         → { items: [Document], nextCursor, hasMore }
GET /v1/documents/{id}   → Document
PUT /v1/documents/{id}   { kind, projectId?, keyVersion, rev, blobRef?, data, key? }
                         If-None-Match: *           new document, rev = 1
                         If-Match: "<baseRev>"      change, rev = baseRev + 1
                         → { rev, cursor }

Document = { id, kind, projectId?, keyVersion, rev, blobRef?, size, writtenBy, updatedAt, data }
```

`data` is the envelope. `updatedAt` is the server's time of the write and is not the `updatedAt` of the payload. There is **no `DELETE`** for documents, as in `SPEC.md`.

- **Creating a project:** the new document has `kind` `project`, `keyVersion` 1 and a `key` = `{ keyVersion, wrapped }`: the project key handed to the caller itself. The server records the caller as owner. Only a user can create a project.
- **Who may write:** a member with role `write` or `owner`. A `read` member only reads. A task document must name a `projectId` the caller may write to, and a `keyVersion` that exists for that project.
- **Loading everything** is `GET /v1/documents` with an empty cursor, repeated with `nextCursor` while `hasMore` is true. The feed holds only documents of projects the caller is a member of. The same call with a saved cursor returns only what changed since. A client reads `GET /v1/projects` first, to have the keys.
- **Noticing changes:** `GET /v1/head` is cheap. A client polls it every 5 to 10 seconds while the app is in front and reloads when `cursor` differs from the one it last saw. This takes the place of the file watcher. A push channel (SSE) may be added later.
- **History:** the server keeps at least the last 10 revisions of every document and may drop older ones. `GET /v1/documents/{id}/revisions` lists `rev`, `keyVersion`, `writtenBy` and time; `GET /v1/documents/{id}/revisions/{rev}` returns one. This replaces `.backup/`. A restore is an ordinary write of the old payload as a new revision.
- A client re-encrypting documents after a revoke writes each one as a normal change with the new `keyVersion`. Documents that are not rewritten stay readable with the older key.

**Blobs** (task images)

```
PUT  /v1/blobs/{blobId}  body: envelope (application/octet-stream)
                         X-Content-SHA256: <hex of the body>
                         X-Oloop-Task: <taskId>
                         → 201 (200 if the same blob is uploaded again)
GET  /v1/blobs/{blobId}  → envelope; ETag is the SHA-256
HEAD /v1/blobs/{blobId}
```

- A blob is immutable. A second `PUT` of the same `blobId` succeeds only with the same hash and the same task, otherwise `409`. A client uses a new `blobId` for every image.
- The task of `X-Oloop-Task` has to exist: its project decides who may upload. An image is therefore added to a task that has been written, and a task cannot be created with a `blobRef`. Without that task, or without access to its project, the answer is `404`.
- The caller needs read access to the project of the task for `GET` and write access for `PUT`.
- The body is an envelope: the server refuses one that is shorter than the fixed parts of an envelope or whose `v` and `alg` are not 1, with `400`. A hash that is not the one of the body is `400`, too.
- A task document may carry a `blobRef` only for a blob that was uploaded for that task; the server refuses a write with another one with `400`.
- Limit: 10 MiB per blob. The server checks the hash after receiving the body, writes to a temporary file in the same directory, flushes, renames, and only then records the blob. A blob is never listed without its file.
- The server keeps blobs as files in its own storage, not in the database. Where is up to the server.

## Images

On this backend `imagePath` of a task is `"blob:<blobId>"` instead of a relative path, and the task document carries the same id as `blobRef`. A path of this form never occurs in a data folder.

- *Add / replace:* encrypt the image with the project key, upload it under a new `blobId`, then write the task with the new `imagePath`, `blobRef`, `updatedAt` and `updatedBy`. If writing the task fails, the uploaded blob is left for the server to remove.
- *Remove:* write the task with `imagePath: null`, `blobRef: null`, and the updated `updatedAt` and `updatedBy`.
- The type is not in the id. A client recognizes it from the decrypted bytes and accepts only `png`, `jpeg`, `gif` and `webp`, as the folder backend does for its extensions.
- A missing blob is not an error: the client shows that the image is missing.
- **Clean-up is the server's job.** A client never deletes a blob. The server removes a blob that was never referenced by a task after 24 hours (an aborted upload), and a blob that the current revision of no document refers to any more after 30 days, counted from the write that dropped it. Writing a revision that refers to it again, a restore for example, starts it anew. Temporary files of aborted uploads go with it.

## Concurrency

`rev` is the revision of a document. A new document has `rev` 1. A change is written with `If-Match: "<baseRev>"` and `rev` = `baseRev + 1`; the server accepts it only if `baseRev` is the stored revision and `rev` is the next one, and answers `409 conflict` otherwise. The revision is part of the associated data, so a client chooses it before it encrypts.

This is the counterpart of the comparison of `updatedAt` in the folder backend and has the same consequences for a client:

- A `409` is shown as a conflict. The user decides between **reload** and **overwrite**; nothing is overwritten silently.
- *Overwrite* loads the current revision, applies the change on top of it and writes with that revision as `baseRev`.
- Whoever shows the conflict gets the `updatedAt` of the other version by decrypting the current document.
- An agent, which has no one to ask, treats a `409` as a failed write: the CLI reports it and exits with an error. It never overwrites by itself.

## Agents

An agent is the identity the CLI uses when an LLM works on behalf of a user: its own key pair, its own token, and access only to the projects the user granted to it. How an agent is created, used, renewed (token and key pair) and revoked, what it can and cannot do, and the API for it are in `AGENTS.md`.

## Threat model

| | |
|---|---|
| **A passive server or someone with its database** | sees the metadata above and ciphertext. Cannot read titles, texts, images or project names |
| **A malicious server** | can withhold, delete, delay, reorder and show an older whole state of a document (a client that has seen a higher `rev` warns). Cannot read or change content undetected. Cannot hand out a key it knows, because keys are authenticated by the sender (see above). Can see who has access to which project |
| **A member with `read`** | holds the project key, so cryptographically can write, too. Only the server stops it |
| **A member** | can write any `createdBy`/`updatedBy`. `writtenBy` is set by the server |
| **A revoked member or agent** | loses access at once. Keeps the keys and data it already had. A new `keyVersion` protects what is written afterwards, and what is re-encrypted |
| **A stolen device or credentials file** | gives its principal's access. A passphrase protects the user's key at rest, an agent's file is only protected by its file mode |
| **Loss of passphrase and recovery code** | the data is gone |

## Limits

| What | Limit |
|---|---|
| Document, as an envelope | 256 KiB |
| Blob | 10 MiB |
| Documents and blobs per user | configurable quota, answered with `413` |

## Conformance

A client that supports this backend must pass the vectors in `fixtures/server/vectors.json`. They are generated by `fixtures/server/generate.py` with the libsodium binding of Python, with fixed keys and nonces, and then fixed; `fixtures/server/README.md` says how to use them. They cover: passphrase to key (Argon2id), the key bundle, an envelope of a document, of a blob and of a wrapped secret key (with their associated data), and the hand-over of a project key (`wrapped`, including the check of `projectId` and `keyVersion`). They are the yardstick for the encryption, as `fixtures/` is for the format.

## Open points

- **Sharing with other people:** the key structure and the member endpoints are meant for it, V1 accepts only agents as members. Missing: finding a user by name, the invitation, the pinning store of the clients and a way to show a fingerprint for comparing it out of band.
- **libsodium in the desktop client:** native libraries for each platform have to go into the packages. The binding must pass the vectors.
- **Push:** SSE instead of polling `GET /v1/head`.
- **Offline use:** a local, encrypted copy that is written to and synchronized later. Until then a client keeps showing what it loaded last and refuses writes with a clear message when the server cannot be reached.
- **Moving between backends:** export a data folder to a server and back. `imagePath` has to be translated (`images/…` ↔ `blob:…`), and a client needs to be able to write a project and a task with the ids it already has.
- **OpenAPI file** for the API above, kept in this repo next to `schemas/`.
- **Rollback detection** across devices is only as good as what one device has seen.
- **Other blob storage** (S3 compatible) behind the same API.
