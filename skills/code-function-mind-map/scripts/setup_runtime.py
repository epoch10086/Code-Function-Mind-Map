"""Prepare dependencies in the skill; never install into the analyzed project."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import venv


def prepare(skill: Path):
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11+ is required')
    runtime = skill / '.runtime' / 'python'
    executable = runtime / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    temporary = skill / '.runtime' / 'tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary), PIP_CACHE_DIR=str(skill / '.runtime' / 'pip-cache'))
    if not executable.exists():
        venv.EnvBuilder(with_pip=False).create(runtime)
    subprocess.run([str(executable), '-m', 'ensurepip', '--upgrade'], env=environment, check=True)
    subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(skill / 'requirements.txt')], env=environment, check=True)
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm:
        raise RuntimeError('Node.js 18+ with npm is required')
    command = 'ci' if (skill / 'package-lock.json').exists() else 'install'
    environment['npm_config_cache'] = str(skill / '.runtime' / 'npm-cache')
    subprocess.run([npm, command, '--ignore-scripts', '--no-audit', '--no-fund'], cwd=skill, env=environment, check=True)
    print('Runtime ready:', executable)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', type=Path, default=Path(__file__).resolve().parents[1])
    prepare(parser.parse_args().skill.resolve())
