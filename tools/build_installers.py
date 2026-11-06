"""Build the Windows installers (MSI and Setup.exe) from the portable release ZIP.

Run tools/build_windows.py first. The installers contain exactly the files in
that ZIP. WiX comes from the pinned .NET local tool in .config/dotnet-tools.json,
and its extensions are pinned to the same version.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WIX_EXTENSIONS = ["WixToolset.UI.wixext", "WixToolset.Util.wixext", "WixToolset.BootstrapperApplications.wixext"]
ZIP_FOLDER = "Room AC Control/"


def version():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def wix_version():
    tools = json.loads((ROOT / ".config" / "dotnet-tools.json").read_text(encoding="utf-8"))
    return tools["tools"]["wix"]["version"]


def release_names(app_version):
    stem = f"Room-AC-Control-for-hOn-{app_version}-Windows-x64"
    return {"zip": f"{stem}.zip", "msi": f"{stem}.msi", "setup": f"{stem}-Setup.exe"}


def stage_files(archive, stage):
    """Unpack the portable ZIP's app folder; refuse anything that would leave `stage`."""
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.startswith(ZIP_FOLDER) or info.is_dir():
                continue
            relative = PurePosixPath(info.filename[len(ZIP_FOLDER):])
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"Unexpected path in the release ZIP: {info.filename}")
            target = stage.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    if not (stage / "runtime" / "RoomACControl" / "RoomACControl.exe").is_file():
        raise RuntimeError("The release ZIP has no runtime/RoomACControl/RoomACControl.exe.")


def license_rtf(text):
    """The MIT licence as plain RTF for the MSI's licence page."""
    escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    escaped = "".join(ch if ord(ch) < 128 else f"\\u{ord(ch)}?" for ch in escaped)
    paragraphs = escaped.replace("\r\n", "\n").split("\n")
    return "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Segoe UI;}}\\fs18\n" + "\\par\n".join(paragraphs) + "}\n"


def logo(target):
    from PIL import Image
    with Image.open(ROOT / "src" / "room_ac_control" / "assets" / "app-icon.png") as image:
        image.convert("RGBA").resize((64, 64), Image.LANCZOS).save(target)


def wix(*args, cwd):
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError("The .NET SDK is required to build the installers (dotnet was not found).")
    subprocess.run([dotnet, "tool", "run", "wix", "--", *args], check=True, cwd=cwd)


def checksums(releases, names):
    lines = [f"{hashlib.sha256((releases / name).read_bytes()).hexdigest()}  {name}\n" for name in names]
    (releases / "SHA256SUMS.txt").write_text("".join(lines), encoding="ascii")


def main():
    if sys.platform != "win32":
        raise RuntimeError("Build the installers on Windows.")
    app_version = version()
    names = release_names(app_version)
    releases = ROOT / "releases"
    archive = releases / names["zip"]
    if not archive.is_file():
        raise RuntimeError(f"Build the portable release first: {archive.name} is missing.")
    work = ROOT / "build" / "installer"
    work.mkdir(parents=True, exist_ok=True)
    stage = work / "stage"
    stage_files(archive, stage)
    (work / "License.rtf").write_text(license_rtf((ROOT / "LICENSE").read_text(encoding="utf-8")), encoding="ascii")
    logo(work / "logo.png")

    subprocess.run([shutil.which("dotnet") or "dotnet", "tool", "restore"], check=True, cwd=ROOT)
    pinned = wix_version()
    # Extensions are cached in build/installer/.wix, outside Git.
    wix("extension", "add", *[f"{name}/{pinned}" for name in WIX_EXTENSIONS], cwd=work)
    icon = ROOT / "src" / "room_ac_control" / "assets" / "app.ico"
    sources = ROOT / "packaging" / "installer"
    msi, setup = releases / names["msi"], releases / names["setup"]
    for stale in (msi, setup):
        stale.unlink(missing_ok=True)
    wix("build", str(sources / "RoomACControl.wxs"), "-arch", "x64",
        "-ext", "WixToolset.UI.wixext", "-ext", "WixToolset.Util.wixext",
        "-d", f"Version={app_version}", "-d", f"StageDir={stage}", "-d", f"Icon={icon}",
        "-d", f"LicenseRtf={work / 'License.rtf'}",
        "-intermediatefolder", str(work / "obj-msi"), "-pdbtype", "none", "-o", str(msi), cwd=work)
    wix("build", str(sources / "Setup.wxs"), "-arch", "x64", "-ext", "WixToolset.BootstrapperApplications.wixext",
        "-d", f"Version={app_version}", "-d", f"Msi={msi}", "-d", f"Icon={icon}", "-d", f"Logo={work / 'logo.png'}",
        "-intermediatefolder", str(work / "obj-setup"), "-pdbtype", "none", "-o", str(setup), cwd=work)
    checksums(releases, [names["zip"], names["msi"], names["setup"]])
    print(f"Installer: {msi}\nInstaller: {setup}", flush=True)


if __name__ == "__main__":
    main()
