"""Build and test with a process-local UCRT64 PATH; never change system settings."""
from pathlib import Path
import argparse
import os
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--configuration', choices=['Debug', 'Release'], default='Debug')
parser.add_argument('--toolchain', default='C:/msys64/ucrt64/bin')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
build = root.parent / 'PulseMetrics_V2_BUILD' / args.configuration.lower()
env = os.environ.copy()
env['PATH'] = str(Path(args.toolchain)) + os.pathsep + env.get('PATH', '')
for command in [
    ['cmake', '-S', str(root), '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=' + args.configuration, '-DBUILD_TESTING=ON',
     '-DCMAKE_C_COMPILER=' + (Path(args.toolchain) / 'gcc.exe').as_posix(),
     '-DCMAKE_MAKE_PROGRAM=' + (Path(args.toolchain) / 'ninja.exe').as_posix()],
    ['cmake', '--build', str(build), '--parallel', '2'],
    ['ctest', '--test-dir', str(build), '--output-on-failure'],
]:
    command[0] = str(Path(args.toolchain) / (command[0] + '.exe'))
    subprocess.run(command, env=env, check=True)
