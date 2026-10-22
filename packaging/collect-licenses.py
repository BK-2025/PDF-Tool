"""Collect installed dependency licenses into the macOS application bundle."""
import importlib.metadata
import shutil
from pathlib import Path
root=Path(__file__).parent/'generated-licenses'
root.mkdir(exist_ok=True)
for name in ('PyMuPDF','Pillow','PyInstaller','pyinstaller-hooks-contrib','altgraph','macholib','packaging'):
    distribution=importlib.metadata.distribution(name)
    target=root/name
    target.mkdir(exist_ok=True)
    found=False
    for entry in distribution.files or []:
        if any(part.upper().startswith(('LICENSE','COPYING','NOTICE')) for part in entry.parts):
            source=Path(distribution.locate_file(entry))
            if source.is_file():
                shutil.copyfile(source,target/source.name)
                found=True
    if not found:
        raise RuntimeError('License file missing for '+name)
shutil.copyfile(Path(__file__).parent/'Python-LICENSE.txt',root/'Python-LICENSE.txt')
shutil.copyfile(Path(__file__).parent/'NOTICE.txt',root/'NOTICE.txt')
