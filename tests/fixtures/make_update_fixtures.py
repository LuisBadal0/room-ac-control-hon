"""Regenerate tests/fixtures/update_manifests.json with a throwaway key.

Needs openssl on PATH. The private key is deleted at the end, so the fixtures
hold only a test public key and pre-signed manifests; nothing here can sign
a real update."""

import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sign(key, data, folder):
    message, signature = folder / "message", folder / "signature"
    message.write_bytes(data)
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(key),
            "-sigopt",
            "rsa_padding_mode:pss",
            "-sigopt",
            "rsa_pss_saltlen:32",
            "-out",
            str(signature),
            str(message),
        ],
        check=True,
    )
    return base64.b64encode(signature.read_bytes()).decode()


def manifest(version, **changes):
    body = {
        "schema": 1,
        "version": version,
        "tag": f"v{version}",
        "archive": f"Room-AC-Control-for-hOn-{version}-Windows-x64.zip",
        "sha256": hashlib.sha256(b"fixture archive").hexdigest(),
        "size": len(b"fixture archive"),
    }
    body.update(changes)
    return json.dumps(body, indent=2).encode()


def main():
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        key, public = folder / "key.pem", folder / "key.pub"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "rsa", "-in", str(key), "-RSAPublicKey_out", "-out", str(public)],
            check=True,
            capture_output=True,
        )
        cases = {
            "valid": manifest("9.9.9"),
            "older": manifest("0.0.1"),
            "schema": manifest("9.9.9", schema=2),
            "archive": manifest("9.9.9", archive="../../evil.zip"),
            "tag": manifest("9.9.9", tag="v9.9.8"),
            "size": manifest("9.9.9", size=10**12),
            "version": manifest("9.9.9-beta"),
        }
        fixtures = {
            "public_key": public.read_text(encoding="ascii"),
            "archive": base64.b64encode(b"fixture archive").decode(),
            "cases": {
                name: {"data": base64.b64encode(data).decode(), "signature": sign(key, data, folder)}
                for name, data in cases.items()
            },
        }
    (HERE / "update_manifests.json").write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
