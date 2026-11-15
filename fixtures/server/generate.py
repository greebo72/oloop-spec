#!/usr/bin/env python3
"""Generates fixtures/server/vectors.json, the test vectors of the server backend.

Everything is deterministic: keys come from fixed seeds and nonces from fixed
labels, so the file is reproducible and a diff of it means a change of the
format. Needs PyNaCl (a binding of libsodium), nothing else.

    python3 generate.py            write vectors.json
    python3 generate.py --check    fail if vectors.json differs from what this
                                   script produces

The vectors follow SERVER.md and AGENTS.md. This script is a test fixture, not
a reference implementation: the point of the file is that every client gets
the same bytes.
"""
import argparse
import base64
import hashlib
import json
import struct
import sys
import uuid
from pathlib import Path

import nacl.bindings as nb
from nacl import pwhash
from nacl.exceptions import CryptoError

OUT = Path(__file__).with_name("vectors.json")

MIB = 1024 * 1024
MIN_M = 19 * MIB
MIN_T = 2


# ---------------- Inputs ----------------

def label(name, size):
    """A fixed value from a label: the first `size` bytes of its SHA-256."""
    return hashlib.sha256(name.encode()).digest()[:size]


def uid(name):
    return uuid.UUID(bytes=label(name, 16), version=4)


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def keypair(name):
    pk, sk = nb.crypto_box_seed_keypair(label("seed " + name, 32))
    return pk, sk


# ---------------- Envelope (SERVER.md, "Envelope") ----------------

def aad(v, alg, *fields):
    """v and alg as bytes, then every field preceded by one 0x00 byte."""
    return bytes([v, alg]) + b"".join(b"\x00" + f.encode() for f in fields)


def seal(key, nonce, associated, plaintext, v=1, alg=1):
    ct = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, associated, nonce, key)
    return bytes([v, alg]) + nonce + ct


def open_envelope(key, envelope, associated):
    if envelope[0] != 1 or envelope[1] != 1:
        raise ValueError("unknown envelope version or algorithm")
    nonce, ct = envelope[2:26], envelope[26:]
    return nb.crypto_aead_xchacha20poly1305_ietf_decrypt(ct, associated, nonce, key)


def doc_aad(kind, doc_id, key_version, rev):
    return aad(1, 1, "doc", kind, str(doc_id), str(key_version), str(rev))


def blob_aad(blob_id, task_id, key_version):
    return aad(1, 1, "blob", str(blob_id), str(task_id), str(key_version))


def key_aad(user_id):
    return aad(1, 1, "key", str(user_id))


# ---------------- Handing keys over (SERVER.md) ----------------

def wrap(project_key, project_id, key_version, recipient_pk, sender_sk, nonce):
    message = project_key + project_id.bytes + struct.pack(">I", key_version)
    return nonce + nb.crypto_box(message, nonce, recipient_pk, sender_sk), message


def unwrap(wrapped, recipient_sk, sender_pk, project_id, key_version):
    """Opens a handed-over key and checks projectId and keyVersion."""
    nonce, box = wrapped[:24], wrapped[24:]
    message = nb.crypto_box_open(box, nonce, sender_pk, recipient_sk)
    if message[32:48] != project_id.bytes:
        raise ValueError("projectId in the message is not the expected one")
    if struct.unpack(">I", message[48:52])[0] != key_version:
        raise ValueError("keyVersion in the message is not the expected one")
    return message[:32]


def box(message, nonce, recipient_pk, sender_sk):
    return nonce + nb.crypto_box(message, nonce, recipient_pk, sender_sk)


def box_open(data, recipient_sk, sender_pk):
    return nb.crypto_box_open(data[24:], data[:24], sender_pk, recipient_sk)


def kdf(passphrase, salt, m, t):
    return pwhash.argon2id.kdf(32, passphrase.encode(), salt, opslimit=t, memlimit=m)


def hx(data):
    return data.hex()


# ---------------- The vectors ----------------

def build():
    user_pk, user_sk = keypair("user")
    agent_pk, agent_sk = keypair("agent 1")
    agent2_pk, agent2_sk = keypair("agent 2")
    server_pk, server_sk = keypair("malicious server")

    user_id = uid("user")
    agent_id = uid("agent")
    project_id = uid("project")
    task_id = uid("task")
    blob_id = uid("blob")
    project_key = label("project key 1", 32)
    project_key_2 = label("project key 2", 32)

    passphrase = "correct horse battery staple"
    salt = label("salt", 16)
    recovery_code = label("recovery code", 32)

    v = {"description": (
        "Test vectors of the server backend (SERVER.md, AGENTS.md). Binary values are "
        "lowercase hex unless a name ends in B64, which is base64url without padding as in "
        "the API. Every nonce is fixed so the file is reproducible. 'mustFail' entries are "
        "inputs a client has to refuse."), "version": 1}

    # --- 1. Passphrase to key
    cases = []
    for name, m, t in (("default", 64 * MIB, 3), ("minimum", MIN_M, MIN_T)):
        cases.append({"name": name, "passphrase": passphrase, "saltHex": hx(salt),
                      "m": m, "t": t, "keyHex": hx(kdf(passphrase, salt, m, t))})
    # How text becomes bytes (SERVER.md, "Key hierarchy"): UTF-8 of the text as typed, no
    # normalization. Texts are given as code points, so that no editor or transport can
    # change the spelling of the vectors themselves.
    def text(code_points):
        return "".join(map(chr, code_points))

    typed = [
        ("u-umlaut as one character (NFC)", [0xFC]),
        ("u followed by a combining diaeresis (NFD)", [0x75, 0x308]),
        ("fi ligature, not folded to fi", [0xFB01]),
        ("fullwidth digit one, not folded to 1", [0xFF11]),
        ("no-break space, not folded to a space", [0x61, 0xA0, 0x62]),
        ("a character outside the basic plane", [0x1F511]),
        ("a german word", [0x4D, 0xFC, 0xDF, 0x69, 0x67]),
        ("spaces at the edges and a double space are kept", [0x20, 0x61, 0x20, 0x20, 0x62, 0x20]),
        ("a line break at the end of a pasted text is kept", [0x61, 0x62, 0x0A]),
    ]
    umlaut_keys = []
    for name, points in typed[:2]:
        umlaut_keys.append({"name": name, "codePoints": points,
                            "keyHex": hx(kdf(text(points), salt, MIN_M, MIN_T))})
    assert umlaut_keys[0]["keyHex"] != umlaut_keys[1]["keyHex"]

    v["kdf"] = {
        "algorithm": "crypto_pwhash, ALG_ARGON2ID13, 32 byte output; m = memlimit in bytes, t = opslimit",
        "encoding": {
            "rule": "the UTF-8 bytes of the text exactly as typed or pasted, no normalization; "
                    "text that is not valid Unicode is refused",
            "cases": [{"name": name, "codePoints": points, "utf8Hex": hx(text(points).encode())}
                      for name, points in typed],
            "refused": [
                {"name": "a lone high surrogate", "codePoints": [0x61, 0xD800]},
                {"name": "a lone low surrogate", "codePoints": [0xDC00]},
            ],
            "keys": {
                "saltHex": hx(salt), "m": MIN_M, "t": MIN_T, "cases": umlaut_keys,
                "note": "the two keys differ: the two spellings are two passphrases",
            },
        },
        "cases": cases,
        "policy": {
            "minM": MIN_M, "minT": MIN_T,
            "cases": [
                {"m": MIN_M, "t": MIN_T, "accept": True},
                {"m": 64 * MIB, "t": 3, "accept": True},
                {"m": MIN_M - 1, "t": MIN_T, "accept": False},
                {"m": MIN_M, "t": MIN_T - 1, "accept": False},
            ],
        },
    }

    # --- 2. Key pairs and the key bundle
    passphrase_key = kdf(passphrase, salt, 64 * MIB, 3)
    n_pass, n_rec = label("nonce wrapped secret key", 24), label("nonce recovery wrapped", 24)
    wrapped_sk = seal(passphrase_key, n_pass, key_aad(user_id), user_sk)
    recovery_wrapped = seal(recovery_code, n_rec, key_aad(user_id), user_sk)
    v["keys"] = {
        "userId": str(user_id),
        "publicKeyHex": hx(user_pk), "secretKeyHex": hx(user_sk),
        "recoveryCodeHex": hx(recovery_code),
        "wrappedSecretKeyHex": hx(wrapped_sk),
        "recoveryWrappedSecretKeyHex": hx(recovery_wrapped),
        "aadHex": hx(key_aad(user_id)),
        # Exactly the JSON the API carries (SERVER.md, "Key bundle"): binary values are
        # base64url without padding.
        "bundle": {
            "v": 1, "kdf": "argon2id", "salt": b64(salt), "m": 64 * MIB, "t": 3,
            "publicKey": b64(user_pk),
            "wrappedSecretKey": b64(wrapped_sk),
            "recoveryWrappedSecretKey": b64(recovery_wrapped),
        },
        "unlock": "Both the passphrase (via kdf.cases[0]) and the recovery code open the "
                  "secret key; the public key belonging to it equals publicKeyHex.",
    }

    # --- 3. Handing a project key over
    def grant(name, key, kv, recipient_pk, sender_sk, sender_pk, recipient_sk):
        nonce = label("nonce grant " + name, 24)
        wrapped, message = wrap(key, project_id, kv, recipient_pk, sender_sk, nonce)
        assert unwrap(wrapped, recipient_sk, sender_pk, project_id, kv) == key
        return {"name": name, "projectId": str(project_id), "keyVersion": kv,
                "projectKeyHex": hx(key), "messageHex": hx(message), "wrappedHex": hx(wrapped),
                "senderPublicKeyHex": hx(sender_pk), "recipientPublicKeyHex": hx(recipient_pk)}

    v["grants"] = {
        "format": "wrapped = nonce(24) | crypto_box_easy(message, nonce, recipientPublicKey, "
                  "senderSecretKey); message = projectKey(32) | projectId(16) | keyVersion(4, big endian)",
        "cases": [
            grant("owner to itself", project_key, 1, user_pk, user_sk, user_pk, user_sk),
            grant("owner to agent", project_key, 1, agent_pk, user_sk, user_pk, agent_sk),
            grant("owner to agent, key version 2", project_key_2, 2, agent_pk, user_sk, user_pk, agent_sk),
        ],
    }

    # --- 4. Documents and a blob
    project_text = (
        f"---\nformatVersion: 1\nid: {project_id}\nname: Example\n"
        "createdAt: 2026-11-14T10:00:00Z\n---\n").encode()
    task_text = (
        f"---\nformatVersion: 1\nid: {task_id}\nprojectId: {project_id}\ntype: todo\n"
        "title: \"Water the plants\"\nstatus: open\nimagePath: \"blob:" + str(blob_id) + "\"\n"
        "createdAt: 2026-11-14T10:05:00Z\ncreatedBy: alice\nupdatedAt: 2026-11-14T10:05:00Z\n"
        "updatedBy: alice\nlabels: [home]\ncomments: []\n---\nEvery Friday, with rain water.\n").encode()

    def document(name, kind, doc_id, kv, rev, key, plaintext):
        nonce = label("nonce document " + name, 24)
        a = doc_aad(kind, doc_id, kv, rev)
        env = seal(key, nonce, a, plaintext)
        assert open_envelope(key, env, a) == plaintext
        return {"name": name, "kind": kind, "id": str(doc_id), "keyVersion": kv, "rev": rev,
                "keyHex": hx(key), "aadHex": hx(a), "nonceHex": hx(nonce),
                "plaintextUtf8": plaintext.decode(), "envelopeHex": hx(env)}

    docs = [
        document("project", "project", project_id, 1, 1, project_key, project_text),
        document("task, third revision", "task", task_id, 1, 3, project_key, task_text),
        document("task after a key rotation", "task", task_id, 2, 4, project_key_2, task_text),
    ]
    v["documents"] = {
        "envelope": "v(1) | alg(1) | nonce(24) | ciphertext+tag; v=1, alg=1 (XChaCha20-Poly1305 IETF)",
        "aad": "v and alg as bytes, then every field preceded by one 0x00 byte: "
               "'doc', kind, id, keyVersion, rev (UUIDs lowercase, numbers decimal)",
        "cases": docs,
    }

    image = b"\x89PNG\r\n\x1a\n" + label("image bytes", 40)
    n_blob = label("nonce blob", 24)
    a_blob = blob_aad(blob_id, task_id, 1)
    blob_env = seal(project_key, n_blob, a_blob, image)
    assert open_envelope(project_key, blob_env, a_blob) == image
    v["blob"] = {
        "blobId": str(blob_id), "taskId": str(task_id), "keyVersion": 1,
        "keyHex": hx(project_key), "aadHex": hx(a_blob), "nonceHex": hx(n_blob),
        "plaintextHex": hx(image), "envelopeHex": hx(blob_env),
        "sha256Hex": hashlib.sha256(blob_env).hexdigest(),
        "aad": "'blob', blobId, taskId, keyVersion, in the same encoding as for documents",
    }

    # --- 5. Agents: registration, rotation of the key pair
    n_reg = label("nonce registration", 24)
    registration = box(agent_pk + agent_id.bytes, n_reg, user_pk, user_sk)
    assert box_open(registration, user_sk, user_pk) == agent_pk + agent_id.bytes

    key_number = 2
    n_stmt = label("nonce statement", 24)
    stmt_message = agent2_pk + agent_id.bytes + struct.pack(">I", key_number)
    statement = box(stmt_message, n_stmt, user_pk, agent_sk)
    assert box_open(statement, user_sk, agent_pk) == stmt_message

    n_self = label("nonce self grant", 24)
    self_wrapped, self_message = wrap(project_key, project_id, 1, agent2_pk, agent2_sk, n_self)
    assert unwrap(self_wrapped, agent2_sk, agent2_pk, project_id, 1) == project_key

    v["agents"] = {
        "agentId": str(agent_id), "userId": str(user_id),
        "userPublicKeyHex": hx(user_pk),
        "key1": {"publicKeyHex": hx(agent_pk), "secretKeyHex": hx(agent_sk)},
        "key2": {"publicKeyHex": hx(agent2_pk), "secretKeyHex": hx(agent2_sk)},
        "registration": {
            "format": "nonce(24) | crypto_box_easy(agentPublicKey(32) | agentId(16), nonce, "
                      "userPublicKey, userSecretKey)",
            "hex": hx(registration),
            "check": "Open with the user's secret key and the user's public key; the message "
                     "is key1.publicKey | agentId.",
        },
        "statement": {
            "format": "nonce(24) | crypto_box_easy(newPublicKey(32) | agentId(16) | keyNumber(4, "
                      "big endian), nonce, userPublicKey, oldAgentSecretKey); keyNumber is the "
                      "number of the NEW key, so the first rotation makes 2",
            "keyNumber": key_number, "hex": hx(statement),
            "check": "Open with the user's secret key and key1.publicKey; the message is "
                     "key2.publicKey | agentId | 2. The chain registration -> statement ends at key2.",
        },
        "selfGrant": {
            "format": "a grant (see 'grants') with recipient = sender = the new key of the agent",
            "projectId": str(project_id), "keyVersion": 1,
            "projectKeyHex": hx(project_key), "wrappedHex": hx(self_wrapped),
            "check": "Open with key2.secretKey and key2.publicKey as the sender.",
        },
    }

    # --- 6. Inputs a client must refuse
    must_fail = []
    doc = docs[1]
    env = bytes.fromhex(doc["envelopeHex"])
    key = bytes.fromhex(doc["keyHex"])

    tampered = env[:-1] + bytes([env[-1] ^ 1])
    must_fail.append({"name": "document with a changed byte", "kind": "envelope",
                      "keyHex": doc["keyHex"], "aadHex": doc["aadHex"], "envelopeHex": hx(tampered),
                      "reason": "the tag does not match"})

    wrong_rev = doc_aad("task", task_id, 1, 4)
    must_fail.append({"name": "revision 3 offered as revision 4", "kind": "envelope",
                      "keyHex": doc["keyHex"], "aadHex": hx(wrong_rev), "envelopeHex": doc["envelopeHex"],
                      "reason": "the revision is part of the associated data"})

    other_doc = doc_aad("task", project_id, 1, 3)
    must_fail.append({"name": "the task offered as another document", "kind": "envelope",
                      "keyHex": doc["keyHex"], "aadHex": hx(other_doc), "envelopeHex": doc["envelopeHex"],
                      "reason": "the id is part of the associated data"})

    for bad_v, bad_alg, why in ((2, 1, "unknown envelope version"), (1, 2, "unknown algorithm")):
        bad = seal(key, label("nonce bad envelope", 24), aad(bad_v, bad_alg, "doc", "task", str(task_id), "1", "3"),
                   b"x", v=bad_v, alg=bad_alg)
        must_fail.append({"name": why, "kind": "envelope-header", "keyHex": doc["keyHex"],
                          "envelopeHex": hx(bad), "reason": why + ": stop and report, never write"})

    forged, _ = wrap(label("key the server knows", 32), project_id, 1, user_pk, server_sk,
                     label("nonce forged", 24))
    must_fail.append({"name": "a key handed over by the server, not by the owner", "kind": "grant",
                      "wrappedHex": hx(forged), "recipientSecretKeyHex": hx(user_sk),
                      "pinnedSenderPublicKeyHex": hx(user_pk),
                      "projectId": str(project_id), "keyVersion": 1,
                      "reason": "opened with the pinned public key of the owner it does not open"})

    other_project = uid("other project")
    wrapped_other, _ = wrap(project_key, other_project, 1, agent_pk, user_sk, label("nonce other project", 24))
    must_fail.append({"name": "a key for another project", "kind": "grant",
                      "wrappedHex": hx(wrapped_other), "recipientSecretKeyHex": hx(agent_sk),
                      "pinnedSenderPublicKeyHex": hx(user_pk),
                      "projectId": str(project_id), "keyVersion": 1,
                      "reason": "it opens, but the projectId in the message is not the expected one"})

    wrapped_kv, _ = wrap(project_key, project_id, 1, agent_pk, user_sk, label("nonce old version", 24))
    must_fail.append({"name": "an old key version offered as version 2", "kind": "grant",
                      "wrappedHex": hx(wrapped_kv), "recipientSecretKeyHex": hx(agent_sk),
                      "pinnedSenderPublicKeyHex": hx(user_pk),
                      "projectId": str(project_id), "keyVersion": 2,
                      "reason": "it opens, but the keyVersion in the message is not the expected one"})

    forged_stmt = box(stmt_message, label("nonce forged statement", 24), user_pk, server_sk)
    must_fail.append({"name": "a statement not made by the old key of the agent", "kind": "statement",
                      "statementHex": hx(forged_stmt), "userSecretKeyHex": hx(user_sk),
                      "previousAgentPublicKeyHex": hx(agent_pk),
                      "reason": "opened with the previous key of the agent it does not open"})

    # every must-fail case really fails with this script's own checks
    def refuses(case):
        try:
            k = case["kind"]
            if k == "envelope":
                open_envelope(bytes.fromhex(case["keyHex"]), bytes.fromhex(case["envelopeHex"]),
                              bytes.fromhex(case["aadHex"]))
            elif k == "envelope-header":
                open_envelope(bytes.fromhex(case["keyHex"]), bytes.fromhex(case["envelopeHex"]), b"")
            elif k == "grant":
                unwrap(bytes.fromhex(case["wrappedHex"]), bytes.fromhex(case["recipientSecretKeyHex"]),
                       bytes.fromhex(case["pinnedSenderPublicKeyHex"]), uuid.UUID(case["projectId"]),
                       case["keyVersion"])
            else:
                box_open(bytes.fromhex(case["statementHex"]), bytes.fromhex(case["userSecretKeyHex"]),
                         bytes.fromhex(case["previousAgentPublicKeyHex"]))
        except (CryptoError, ValueError):
            return True
        return False

    for case in must_fail:
        assert refuses(case), "does not fail: " + case["name"]
    v["mustFail"] = must_fail
    return v


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="fail if vectors.json differs from what this script produces")
    args = parser.parse_args()

    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("vectors.json is out of date: run generate.py", file=sys.stderr)
            return 1
        print("vectors.json is up to date")
        return 0

    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
