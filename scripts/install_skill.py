"""Install skill sources to Codex and prepare an isolated runtime."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys


def install(target):
    source=Path(__file__).resolve().parents[1]/'skills/code-function-mind-map'
    if target.exists():
        raise ValueError('Destination already exists; preserve it and select a fresh --target: '+str(target))
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('.runtime','node_modules','__pycache__','*.pyc'))
    subprocess.run([sys.executable,str(target/'scripts/setup_runtime.py')],check=True)
    print('Installed:',target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    codex=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    parser.add_argument('--target',type=Path,default=codex/'skills/code-function-mind-map')
    install(parser.parse_args().target.resolve())
