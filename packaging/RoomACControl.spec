from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
data = [(str(root / 'src' / 'room_ac_control' / 'assets'), 'room_ac_control/assets')]
data += collect_data_files('pyhon')
hidden = collect_submodules('pyhon') + collect_submodules('awsiot') + collect_submodules('awscrt')
hidden += ['pystray._win32', 'room_ac_control.demo']

analysis = Analysis([str(root / 'tools' / 'run.py')],pathex=[str(root / 'src')],
                    datas=data,hiddenimports=hidden,
                    excludes=['pytest','tests','imageio_ffmpeg','pystray._darwin','pystray._gtk',
                              'pystray._appindicator','pystray._xorg'],
                    module_collection_mode={'pystray':'py'})
archive = PYZ(analysis.pure)
executable = EXE(archive,analysis.scripts,[],exclude_binaries=True,name='RoomACControl',
                 debug=False,strip=False,upx=False,console=False,
                 icon=str(root / 'src' / 'room_ac_control' / 'assets' / 'app.ico'),
                 version=str(root / 'packaging' / 'version_info.txt'))
bundle = COLLECT(executable,analysis.binaries,analysis.datas,strip=False,upx=False,name='RoomACControl')
