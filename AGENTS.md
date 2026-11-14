# AGENTS — agent identities for the CLI in the server backend

**Status:** DRAFT (2026-11-14). Part of `SERVER.md`, which defines the principals, the encryption, the project keys and the API this document builds on. Only the server backend has agents; the folder backend has none.

An agent is the way the CLI is used by an LLM on behalf of a user without giving the LLM the user's identity. Whatever the agent holds, the LLM can use, so the agent holds as little as possible, and everything it holds can be renewed or revoked without touching the user's own keys.

## What an agent is

- A principal of kind `agent` (see `SERVER.md`, "Principals"). It belongs to exactly one user, who creates it.
- It has its own X25519 key pair and its own token. It sees only the projects that were granted to it, with the role `write` or `read`.
- It is never deleted, only revoked, so that `writtenBy` stays meaningful.

## The credentials file

The only thing an agent holds. A JSON file with the mode `0600`, written atomically (temporary file, then replace):

```
{ server, agentId, token, publicKey, secretKey, owner: { id, publicKey } }
```

It never holds the user's passphrase, the user's secret key, the recovery code or the keys of projects that were not granted to it. `owner.publicKey` comes from the user's own client when the agent is created; it is what the agent checks every key it receives against (see `SERVER.md`, "Handing a project key to a principal").

## Creating an agent

Done by the user, at a terminal, in their own client, because it needs the user's secret key:

1. The client generates a key pair for the agent.
2. It registers the agent (`POST /v1/agents`) and gets the token. In the same request it sends a **registration**: `nonce` followed by `crypto_box_easy(agentPublicKey | agentId, nonce, userPublicKey, userSecretKey)`. Only the user's key can make it, so the server cannot invent an agent key. A client on another device of the user starts from this and needs no copied pin.
3. For each project the user names, it opens the project key and hands it to the agent (`PUT /v1/projects/{id}/members/{agentId}`), sender = the user, with a role.
4. It writes the credentials file and tells the user where it is. Nothing else leaves the user's client.

For example `oloop agent add claude --project <name> --project <name> [--read-only] [--expires 90d] [--renew-until 1y | --no-renew]`.

## Using an agent

The CLI is told where the file is: `OLOOP_AGENT_CREDENTIALS`, or the option `--credentials FILE`. With it the CLI acts only as the agent: it opens no user key, reads no user secret from the operating system's secret store, and when the file is unusable it fails instead of falling back to the user.

## What an agent cannot do

The server refuses: creating projects, creating or revoking agents, changing the user's key bundle, adding or removing members, reading or writing a project that was not granted to it, writing in a project granted as `read`. It can read and write tasks and comments and set an image, as the CLI can on a data folder.

The two things an agent may do **about itself** are renewing its token and rotating its key pair, below.

## Renewing the token

A token has an expiry (`--expires`, default 90 days). The agent renews it itself:

```
oloop agent renew
```

The CLI calls `POST /v1/agent/renew` with the current token and writes the new token into the credentials file, replacing it atomically. The rules, all enforced by the server:

- The new token is valid for the same time as the original (`lifetime`), counted from now, but never beyond `renewUntil`. `renewUntil` is fixed when the agent is created (default one year after creation, `--renew-until`), so a stolen token cannot be renewed forever. `--no-renew` sets it to the first expiry.
- An expired, revoked or non-renewable token cannot be renewed. Then the user issues a new one: `oloop agent renew <name>` as the user, which writes a new credentials file (`POST /v1/agents/{id}/token`) and starts a new renewal period. A revoked agent stays revoked.
- The old token stays valid for 10 minutes after a renewal, so a lost response does not lock the agent out.
- **Renewal is never automatic.** The CLI renews only when it is told to, and it says how long the token is valid. An agent that renewed silently would live on without the user noticing. The CLI warns on every run when the token expires within 14 days.

## Rotating the key pair

```
oloop agent renew --keypair
```

renews the token as above and replaces the agent's key pair. The agent needs no help of the user for this, because it can open its own keys with the old secret key. In one step (`PUT /v1/agent/keypair`, atomic: all or nothing):

1. The agent generates a new key pair.
2. For every project it is a member of, it opens every key version it holds with the old secret key, checking the sender as always, and hands each one to **itself**: `crypto_box_easy`, recipient = the new public key, sender = the new secret key, `grantedBy` = the agent. The server cannot forge this, because it does not have the new secret key. The server refuses the change unless the new keys cover every project and every key version the agent has.
3. It makes a **statement** for the user: `nonce` followed by `crypto_box_easy(newPublicKey | agentId | keyNumber, nonce, userPublicKey, oldSecretKey)`, with `keyNumber` counting the key pairs of the agent from 1 (4 bytes, big endian). Only the old key of the agent can make it, so it proves that the new key comes from the agent that the user created.
4. The server stores the new public key and appends the statement to the **key chain** of the agent.
5. The agent writes the new credentials file.

The user's client checks the chain before it relies on the agent's public key, for example when it grants another project to the agent: it starts at the registration, opens every statement with the key before it and arrives at the current key. A chain that does not check out is shown as a warning, and the client grants nothing to that agent until the user has decided. The chain is also what a client on another device of the user uses, so no pin is passed around.

A rotation changes the identity of the agent. It does **not** change the project keys: whoever had the old secret key, and the project keys that went with it, still knows those. If the old credentials may have leaked, the user revokes the agent and rotates the project keys, see Revoking.

## Who wrote what

The server records the principal of every revision (`writtenBy`) and clients show it, so a change made by an agent is recognizable as such. The `createdBy`/`updatedBy` inside the payload stay free text as in `SPEC.md`; an agent's default is its name (the CLI takes `$OLOOP_ACTOR` first, as always). A member can write any text there, so only `writtenBy` is evidence.

## Revoking

`oloop agent revoke <name>` ends the token and the memberships at once. The agent still knows the project keys it was given and could read ciphertext it kept or someone hands it. For a thorough revoke the user's client raises the `keyVersion` of the affected projects (`POST /v1/projects/{id}/revoke` with `newKey`) and re-encrypts their documents. The CLI offers this and says what it does not cover.

## The user's own CLI use

The CLI as a user needs the secret key. It does not keep an unlocked key between runs by default. `oloop unlock [--timeout 15m]` is an explicit, time-limited opt-in. Management commands (`agent add`, `agent revoke`, `agent renew <name>`, key and passphrase changes) always ask for the passphrase on a terminal and never take it from an option or an environment variable.

## Limits of the isolation

A process that runs as the same operating-system user can reach what that user can reach: the credentials file and an unlocked session. Real separation of an LLM from the user's identity needs it to run under another operating-system user, in a container or in a sandbox. The agent identity is what makes that separation possible and keeps the damage to the granted projects; it is not a sandbox. Task texts are input that someone else may have written, so an agent reads them as untrusted. The mitigation is the scope: grant only the projects it needs, and `read` where it does not need to write.

## API

Authentication as in `SERVER.md`; the agent token is the bearer token. Errors as there.

```
POST /v1/agents                { name, publicKey, registration,
                                 expiresAt?, renewUntil? }     (user)
                               → { agentId, token }
GET  /v1/agents                (user)
                               → [{ id, name, publicKey, registration,
                                    keyChain: [{ publicKey, statement }],
                                    createdAt, expiresAt, renewUntil, lastUsedAt, revoked }]
POST /v1/agents/{id}/revoke    (user)
POST /v1/agents/{id}/token     (user)  → { token, expiresAt }

POST /v1/agent/renew           (agent) → { token, expiresAt }
PUT  /v1/agent/keypair         (agent)
                               { publicKey, statement,
                                 keys: [{ projectId, keyVersion, wrapped }] }
                               → { token, expiresAt }
```

`token` is shown once; the server keeps only its hash. Revoking ends the token and removes every membership of the agent. A rotation of the key pair returns a fresh token like a renewal does.

## Conformance

The vectors in `fixtures/server/` (see `SERVER.md`) include a registration, a statement and a self-granted key of a rotation, so a client and the CLI can check the chain the same way.

## Open points

- **Default lifetime:** whether 90 days for a token and one year for the renewal period are right.
- **Lost credentials file:** the user issues a new token (`POST /v1/agents/{id}/token`); the agent's key pair is gone with the file, so the user makes a new agent. A way to hand an existing agent a new key pair is not specified.
- **Several agents on one project:** nothing special is needed; every agent has its own entry. A view that shows which agent changed what comes with the clients.
