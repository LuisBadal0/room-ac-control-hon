"""Build a relocatable Windows folder and release ZIP, with dependency notices."""
from importlib import metadata
from pathlib import Path
import json
import shutil
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]


def licenses(destination):
    destination.mkdir(parents=True,exist_ok=True)
    pending=['pyhOn','pystray','Pillow','setuptools','packaging','pyinstaller']
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
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(ROOT/'runtime'),
                    '--workpath',str(ROOT/'build'/'pyinstaller'),str(ROOT/'packaging'/'RoomACControl.spec')],check=True,cwd=ROOT)
    runtime=ROOT/'runtime'/'RoomACControl'
    licenses(runtime/'licenses')
    report=ROOT/'build'/'portable-self-test.json'
    check=subprocess.run([str(runtime/'RoomACControl.exe'),'--self-test',str(report)],timeout=60)
    if check.returncode or not json.loads(report.read_text(encoding='utf-8'))['ok']:
        raise RuntimeError('Portable runtime self-test failed. See build/portable-self-test.json.')
    releases=ROOT/'releases'
    releases.mkdir(exist_ok=True)
    archive=releases/'Room-AC-Control-for-hOn-0.1.1-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        prefix=Path('Room AC Control')
        for name in ['Start Room AC Control.cmd','README.md','LICENSE','THIRD_PARTY_NOTICES.md','SECURITY.md','CONTRIBUTING.md']:
            bundle.write(ROOT/name,str(prefix/name))
        for directory in ['docs/images']:
            for file in sorted((ROOT/directory).rglob('*')):
                if file.is_file():bundle.write(file,str(prefix/file.relative_to(ROOT)))
        bundle.write(ROOT/'docs'/'USER_GUIDE.md',str(prefix/'docs'/'USER_GUIDE.md'))
        for file in sorted(runtime.rglob('*')):
            if file.is_file():bundle.write(file,str(prefix/file.relative_to(ROOT)))
    # A local shortcut is generated separately by Create-Shortcut.ps1; .lnk files
    # contain machine paths and are intentionally absent from Git and the ZIP.
    print(f'Portable release: {archive}',flush=True)


if __name__=='__main__':main()
