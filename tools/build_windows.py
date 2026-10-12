"""Build a relocatable Windows folder and release ZIP, with dependency notices."""
from importlib import metadata
from pathlib import Path
import json
import hashlib
import os
import platform
import re
import tomllib
import shutil
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]


def verify_dependencies():
    from install_dependencies import lock_digests
    marker=Path(sys.prefix)/'room-ac-ready'
    if not marker.exists() or json.loads(marker.read_text(encoding='utf-8')) != lock_digests(True):
        raise RuntimeError('Run tools/install_dependencies.py --build to verify all locked packages first.')
    for file in (ROOT/'requirements.lock',ROOT/'packaging'/'requirements-build.lock'):
        for name,version in re.findall(r'^([\w-]+)==([^\s]+)',file.read_text(encoding='utf-8'),re.MULTILINE):
            if metadata.version(name)!=version:raise RuntimeError(f'Installed version differs from lock: {name}')


def build_manifest(runtime):
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    # Published builds require a Git checkout; no absolute local paths or account data.
    version=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    if os.environ.get('GITHUB_REF_TYPE')=='tag' and os.environ.get('GITHUB_REF_NAME')!=f'v{version}':
        raise RuntimeError('Release tag must match the app version.')
    source=git('rev-parse','HEAD')
    dirty=bool(git('status','--porcelain'))
    if os.environ.get('GITHUB_ACTIONS')=='true' and dirty:
        raise RuntimeError('CI release builds must use a clean source checkout.')
    powershell=shutil.which('pwsh') or shutil.which('powershell')
    if not powershell:raise RuntimeError('PowerShell is required to verify executable signatures.')
    signature_command=[powershell,'-NoProfile','-File',str(ROOT/'tools'/'Sign-Executable.ps1'),
                       '-Path',str(runtime/'RoomACControl.exe')]
    certificate=os.environ.get('ROOM_AC_SIGNING_CERT_THUMBPRINT')
    if certificate:
        signature_command += ['-Thumbprint',certificate]
        if timestamp:=os.environ.get('ROOM_AC_TIMESTAMP_SERVER'):
            signature_command += ['-TimestampServer',timestamp]
        signature=json.loads(subprocess.check_output(signature_command,text=True))
    else:
        # A read-only cmdlet query needs no script execution-policy changes.
        quoted=str(runtime/'RoomACControl.exe').replace("'","''")
        status=subprocess.check_output([powershell,'-NoProfile','-NonInteractive','-Command',
            f"(Get-AuthenticodeSignature -LiteralPath '{quoted}').Status.ToString()"],text=True).strip()
        signature={'status':status}
    files={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
           for name in git('ls-files').splitlines() if (ROOT/name).is_file()}
    manifest={'source_commit':source,'source_dirty':dirty,'source_sha256':files,
              'python_version':platform.python_version(),'pip_version':metadata.version('pip'),'platform':'Windows x64',
              'build_provider':'github-actions' if os.environ.get('GITHUB_ACTIONS')=='true' else 'local',
              'authenticode_status':signature['status'],
              'executable_sha256':hashlib.sha256((runtime/'RoomACControl.exe').read_bytes()).hexdigest(),
              'dependencies':json.loads((runtime/'licenses'/'DEPENDENCIES.json').read_text(encoding='utf-8'))}
    (runtime/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


def licenses(destination):
    destination.mkdir(parents=True,exist_ok=True)
    pending=['pyhOn','pystray','Pillow','setuptools','wheel','packaging','pyinstaller']
    seen=set()
    manifest=[]
    while pending:
        name=pending.pop()
        distribution=metadata.distribution(name)
        key=distribution.metadata['Name'].lower().replace('_','-')
        if key in seen:continue
        seen.add(key)
        manifest.append({'name':distribution.metadata['Name'],'version':distribution.version})
        for requirement_text in distribution.requires or []:
            requirement=Requirement(requirement_text)
            if requirement.marker is None or requirement.marker.evaluate({'extra':''}):
                pending.append(requirement.name)
        for item in distribution.files or []:
            if any(part.upper().startswith(('LICENSE','COPYING','NOTICE')) for part in item.parts):
                source=Path(distribution.locate_file(item))
                if source.is_file():
                    target=destination/key/str(item).replace('\\','/')
                    if not target.resolve().is_relative_to(destination.resolve()):
                        raise RuntimeError('A dependency notice path left the release directory.')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copy2(python_license,destination/'PYTHON-LICENSE.txt')
    for library in ('tcl8.6','tk8.6'):
        license_file=Path(sys.base_prefix)/'tcl'/library/'license.terms'
        if license_file.exists():shutil.copy2(license_file,destination/f'{library}-license.terms')
    shutil.copytree(ROOT/'packaging'/'licenses',destination/'upstream',dirs_exist_ok=True)
    (destination/'DEPENDENCIES.json').write_text(json.dumps(sorted(manifest,key=lambda item:item['name']),indent=2),encoding='utf-8')


def main():
    if sys.platform!='win32':raise RuntimeError('Build this release on Windows.')
    if sys.maxsize<=2**32:raise RuntimeError('Use 64-bit Python for a Windows x64 build.')
    verify_dependencies()
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(ROOT/'runtime'),
                    '--workpath',str(ROOT/'build'/'pyinstaller'),str(ROOT/'packaging'/'RoomACControl.spec')],check=True,cwd=ROOT)
    runtime=ROOT/'runtime'/'RoomACControl'
    licenses(runtime/'licenses')
    build_manifest(runtime)
    report=ROOT/'build'/'portable-self-test.json'
    check=subprocess.run([str(runtime/'RoomACControl.exe'),'--self-test',str(report)],timeout=60)
    if check.returncode or not json.loads(report.read_text(encoding='utf-8'))['ok']:
        raise RuntimeError('Portable runtime self-test failed. See build/portable-self-test.json.')
    releases=ROOT/'releases'
    releases.mkdir(exist_ok=True)
    version=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    archive=releases/f'Room-AC-Control-for-hOn-{version}-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        prefix=Path('Room AC Control')
        for name in ['Start Room AC Control.cmd','README.md','LICENSE','THIRD_PARTY_NOTICES.md','SECURITY.md','CONTRIBUTING.md']:
            bundle.write(ROOT/name,str(prefix/name))
        for directory in ['docs/images']:
            for file in sorted((ROOT/directory).rglob('*')):
                if file.is_file():bundle.write(file,str(prefix/file.relative_to(ROOT)))
        bundle.write(ROOT/'docs'/'USER_GUIDE.md',str(prefix/'docs'/'USER_GUIDE.md'))
        bundle.write(ROOT/'docs'/'BUILD_VERIFICATION.md',str(prefix/'docs'/'BUILD_VERIFICATION.md'))
        for file in sorted(runtime.rglob('*')):
            if file.is_file():bundle.write(file,str(prefix/file.relative_to(ROOT)))
    # A local shortcut is generated separately by Create-Shortcut.ps1; .lnk files
    # contain machine paths and are intentionally absent from Git and the ZIP.
    print(f'Portable release: {archive}',flush=True)
    (releases/'SHA256SUMS.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='ascii')


if __name__=='__main__':main()
