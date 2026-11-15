# Test vectors of the server backend

`vectors.json` holds the test vectors for the encryption of the server backend
(`../../SERVER.md`, `../../AGENTS.md`). A client that supports the backend, and
the server where it touches the formats, must reproduce them. They are what
makes two implementations in two languages produce the same bytes.

Binary values are lowercase hex, except inside `bundle`, which is the JSON of the API and holds
base64url without padding. Every key and every nonce is fixed, so the file is
reproducible.

| Section | What to check |
|---|---|
| `kdf` | Argon2id of the passphrase gives `keyHex`. `policy` lists the parameters a client must accept or refuse. `encoding` pins how typed text becomes bytes: UTF-8, **no normalization** (`utf8Hex` of each text, given as code points), text that is not valid Unicode is refused (`refused`), and the two spellings of an umlaut give two different keys (`keys`) |
| `keys` | the passphrase key and the recovery code both open the wrapped secret key; the public key of the secret key equals `publicKeyHex`. `bundle` is the key bundle exactly as the API carries it: `PUT /v1/keys` takes it, `GET /v1/keys` returns it |
| `grants` | opening a handed-over project key with the recipient's secret key and the sender's public key gives `projectKeyHex`, with the right `projectId` and `keyVersion` in the message |
| `documents` | decrypting `envelopeHex` with `keyHex` and `aadHex` gives the plaintext. A client also builds `aadHex` itself from kind, id, keyVersion and rev and must arrive at the same bytes. Building the envelope with `nonceHex` must give `envelopeHex` |
| `blob` | the same for an image, and `sha256Hex` is the SHA-256 of the envelope |
| `agents` | the registration, the statement of a key rotation and the self-granted key of the agent open as described in `check` |
| `mustFail` | each entry has to be refused. `reason` says why |

Two details the vectors pin down: the associated data is `v`, `alg`, then every
field preceded by one `0x00` byte; and `keyNumber` in a statement is the number
of the new key.

## Regenerating

`generate.py` needs PyNaCl (a binding of libsodium) and nothing else:

```
pip install pynacl
python3 generate.py            # writes vectors.json
python3 generate.py --check    # fails if vectors.json is not what the script produces
```

A change of the vectors is a change of the format. Change `SERVER.md`,
`AGENTS.md`, the script and `vectors.json` together in one commit.
