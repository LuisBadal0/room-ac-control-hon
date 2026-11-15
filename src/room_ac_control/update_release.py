"""The signed update manifest, and downloading and checking a release.

Network and file work for `updates`: reading the signed manifest, streaming a
release file against its signed size and SHA-256, unpacking it and self-testing it.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .diagnostics import diagnostics

REPOSITORY = "LuisBadal0/room-ac-control-hon"
MANIFEST_URL = f"https://github.com/{REPOSITORY}/releases/latest/download/update.json"
SIGNATURE_URL = MANIFEST_URL + ".sig"
EXECUTABLE = "RoomACControl.exe"
ZIP_RUNTIME = "Room AC Control/runtime/RoomACControl/"
MAX_MANIFEST = 16 * 1024
MAX_SIGNATURE = 4096
MAX_ARCHIVE = 400 * 1024 * 1024
MAX_INSTALLER = 400 * 1024 * 1024
MAX_UNPACKED = 1024 * 1024 * 1024
# How this copy was installed -> the manifest field naming that installer.
INSTALLERS = {"msi": "installer", "setup": "setup"}
INSTALL_KEY = r"Software\RoomACControl\Installer"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
# packaging/installer/Setup.wxs; a Setup.exe install registers this bundle for the user.
BUNDLE_UPGRADE_CODE = "{3CE84886-4F75-40A5-B136-E82F9D22EA78}"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CHECK_EVERY_MS = 24 * 60 * 60 * 1000
FIRST_CHECK_MS = 20 * 1000

# The matching private key is held only as the UPDATE_SIGNING_KEY secret in CI
# (packaging/update-signing-key.pub is the same key, for the release workflow).
PUBLIC_KEY = b"""-----BEGIN RSA PUBLIC KEY-----
MIIBigKCAYEArk9pJ2YW7Vsg30XWNkMoX+4WdNmzf29XJtsg3LrX5uT0gU2LV0Ef
UBMyyBUj5rmcJflTbnCyFbVfgwOsKelCfeonINm6kmeLEUoMJ6QVwWsbbpeRAwjI
8Hm+2UStXE2QnaL2ktccvvT0vwqmEdEk3RPaG/oVX//fvrtPUZut14j7YOyvc4DX
ZRbCFUvGp4gyZwXRCJY4ELbfLBlXSodO0t7JEYN043BdLn6Ue7o8cXJj2YXRERtO
LoGMkRF5Ezkk/+U/XTo34CnFxfsHxTFrsQzKNFAqNyBUg4acrtplzGNhvziBzKFf
0h+2z8PIcDJKLID7aqrk1krOCId43+fAym5yh7GhlWc4xf0fAMh4rleT2kRBhcRv
Ndz34jlaHsgDAOWhas432b7NfSfDvrTgp5ywuBBl2+Qp1Fe+z6Hakb3Wrqrk1cpW
LD5/uU8JkMciKvQbxz5C3AP18PUGxqQn4915oxJCqu6gOR7UHGySkf3l2ffEVHMn
IOrVxbYpqqELAgMBAAE=
-----END RSA PUBLIC KEY-----
"""

VERSION = re.compile(r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})$")


class UpdateError(Exception):
    """A user-facing reason the update stopped; the installed app is unchanged."""


def parse_version(text):
    match = VERSION.match(text) if isinstance(text, str) else None
    if not match:
        raise UpdateError("The update information is not valid.")
    return tuple(int(part) for part in match.groups())


def verify_signature(data, signature, public_key=PUBLIC_KEY):
    """RSA-PSS SHA-256, checked with awscrt, which the app already ships for MQTT."""
    from awscrt.crypto import RSA, RSASignatureAlgorithm

    try:
        key = RSA.new_public_key_from_pem_data(public_key)
        valid = key.verify(RSASignatureAlgorithm.PSS_SHA256, hashlib.sha256(data).digest(), signature)
    except (ValueError, RuntimeError):
        valid = False
    if not valid:
        raise UpdateError("The update is not signed by Room AC Control. It was not installed.")


def read_manifest(data, signature, public_key=PUBLIC_KEY):
    """Verify, then validate every field; nothing unsigned is ever parsed."""
    verify_signature(data, signature, public_key)
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise UpdateError("The update information is not valid.") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise UpdateError("This update needs a newer Room AC Control. Download it from the releases page.")
    version = manifest.get("version")
    parse_version(version)
    archive, digest, size = manifest.get("archive"), manifest.get("sha256"), manifest.get("size")
    if (
        manifest.get("tag") != f"v{version}"
        or archive != f"Room-AC-Control-for-hOn-{version}-Windows-x64.zip"
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 0 < size <= MAX_ARCHIVE
    ):
        raise UpdateError("The update information is not valid.")
    return {
        "version": version,
        "tag": manifest["tag"],
        "archive": archive,
        "sha256": digest,
        "size": size,
        "url": download_url(manifest["tag"], archive),
        "notes": f"https://github.com/{REPOSITORY}/releases/tag/{manifest['tag']}",
        "installers": signed_installers(manifest, version),
    }


def download_url(tag, name):
    return f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"


def installer_name(kind, version):
    suffix = ".msi" if kind == "msi" else "-Setup.exe"
    return f"Room-AC-Control-for-hOn-{version}-Windows-x64{suffix}"


def signed_installers(manifest, version):
    """The optional signed MSI and Setup.exe entries; releases before 0.6.0 have none."""
    found = {}
    for kind, field in INSTALLERS.items():
        entry = manifest.get(field)
        if entry is None:
            continue
        name = installer_name(kind, version)
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        size = entry.get("size") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or entry.get("name") != name
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 < size <= MAX_INSTALLER
        ):
            raise UpdateError("The update information is not valid.")
        found[kind] = {"name": name, "sha256": digest, "size": size, "url": download_url(manifest["tag"], name)}
    return found


def is_newer(release, current):
    return parse_version(release["version"]) > parse_version(current)


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        if not url.lower().startswith("https://"):
            raise UpdateError("The update download was redirected to an insecure address.")
        return super().redirect_request(request, fp, code, message, headers, url)


_opener = urllib.request.build_opener(HttpsOnly)


def open_url(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "RoomACControl-Updater"})
    return _opener.open(request, timeout=timeout)


def fetch(url, limit, opener=open_url):
    with opener(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("The update information is not valid.")
    return data


def check(current, opener=open_url, public_key=PUBLIC_KEY):
    """Return the signed release if it is newer than `current`, else None."""
    data = fetch(MANIFEST_URL, MAX_MANIFEST, opener)
    signature = fetch(SIGNATURE_URL, MAX_SIGNATURE, opener)
    release = read_manifest(data, signature, public_key)
    return release if is_newer(release, current) else None


def download(release, folder, progress=lambda done, total: None, cancelled=lambda: False, opener=open_url):
    """Stream the ZIP to disk, enforcing the signed size and SHA-256."""
    item = {"name": release["archive"], **{key: release[key] for key in ("url", "size", "sha256")}}
    return download_file(item, folder, progress, cancelled, opener)


@contextmanager
def local_step():
    """Disk work for an update. A failure here is this computer's (a full disk, a folder
    that cannot be written), so it must not be reported as a network problem."""
    try:
        yield
    except (OSError, zipfile.BadZipFile, shutil.Error) as error:
        diagnostics.record("update_failed", error)
        raise UpdateError(
            "The update could not be saved on this computer. Check free disk space and try again."
        ) from None


def download_file(release, folder, progress=lambda done, total: None, cancelled=lambda: False, opener=open_url):
    """Stream one signed release file (name, url, size, sha256) to disk."""
    with local_step():
        folder.mkdir(parents=True, exist_ok=True)
    target = folder / release["name"]
    partial = target.with_name(target.name + ".part")
    digest, done = hashlib.sha256(), 0
    try:
        with opener(release["url"], timeout=60) as response:
            with local_step():
                handle = partial.open("wb")
            with handle:
                while True:
                    if cancelled():
                        raise UpdateError("The update was cancelled.")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > release["size"]:
                        raise UpdateError("The downloaded update does not match its signature. It was not installed.")
                    digest.update(chunk)
                    with local_step():
                        handle.write(chunk)
                    progress(done, release["size"])
        if done != release["size"] or digest.hexdigest() != release["sha256"]:
            raise UpdateError("The downloaded update does not match its signature. It was not installed.")
        with local_step():
            os.replace(partial, target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def extract_runtime(archive, target):
    """Unpack only runtime/RoomACControl from the release ZIP into `target`."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    unpacked = 0
    with zipfile.ZipFile(archive) as bundle:
        members = [info for info in bundle.infolist() if info.filename.startswith(ZIP_RUNTIME)]
        for info in members:
            relative = PurePosixPath(info.filename[len(ZIP_RUNTIME) :])
            mode = (info.external_attr >> 16) & 0o170000
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
                or any(":" in part or "\\" in part for part in relative.parts)
                or mode == 0o120000
            ):
                raise UpdateError("The update contains unsafe file names. It was not installed.")
            unpacked += info.file_size
            if unpacked > MAX_UNPACKED:
                raise UpdateError("The update is larger than expected. It was not installed.")
            destination = target.joinpath(*relative.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, destination.open("wb") as handle:
                shutil.copyfileobj(source, handle, 1024 * 1024)
    if not (target / EXECUTABLE).is_file():
        raise UpdateError("The update is incomplete. It was not installed.")


def self_test(runtime, version, run=subprocess.run):
    """The new version must start, pass its offline checks and report its version."""
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "self-test.json"
        try:
            result = run(
                [str(runtime / EXECUTABLE), "--self-test", str(report)],
                timeout=120,
                creationflags=NO_WINDOW,
            )
            outcome = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            outcome, result = {}, None
    if not (
        result is not None
        and result.returncode == 0
        and outcome.get("ok") is True
        and outcome.get("version") == version
        and outcome.get("updates") is True
    ):
        raise UpdateError("The new version did not pass its checks. Nothing was changed.")
