#!/usr/bin/env python3
"""Build the Windows x64 portable ZIP on any OS. No binary files enter Git."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    'ghdl.zip': {
        'url': 'https://github.com/ghdl/ghdl/releases/download/v6.0.0/ghdl-mcode-6.0.0-ucrt64.zip',
        'sha256': '76e160ceec35834c73ada6e4e484416d13aed4b64cbc7c74c5cca53a7ef60e41',
    },
    'python.nupkg': {
        'url': 'https://www.nuget.org/api/v2/package/python/3.13.7',
        # SHA512 from NuGet's official package metadata (PackageHash).
        'sha512_base64': '1X7TBUVp/0x51bgfu1zKMthvYHiHt5mYaSkKSxH61fXfdgYb257Idd5rKsh0GAZ/3DOcdDH084hesuGmPJaE2g==',
    },
    'ghdl-source.tar.gz': {
        'url': 'https://github.com/ghdl/ghdl/archive/refs/tags/v6.0.0.tar.gz',
        'sha256': '2d84fbd0b238a26928e89a0256274072c6b40af1969a4f4c7be57ec3515bc622',
    },
}


def verified(path, info):
    data = path.read_bytes()
    if 'sha256' in info:
        matches = hashlib.sha256(data).hexdigest() == info['sha256']
    else:
        matches = base64.b64encode(hashlib.sha512(data).digest()).decode() == info['sha512_base64']
    if not matches:
        raise ValueError('Checksum mismatch; refusing to use ' + path.name)


def fetch(cache):
    cache.mkdir(parents=True, exist_ok=True)
    for name, info in ASSETS.items():
        path = cache/name
        if not path.exists():
            print('Downloading', info['url'], flush=True)
            partial = cache/(name+'.partial')
            with urllib.request.urlopen(info['url'], timeout=60) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out)
            verified(partial, info)
            partial.replace(path)
        verified(path, info)
        print('Verified', name, flush=True)


def extract(archive, dest, prefix=''):
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not item.filename.startswith(prefix) or item.is_dir():
                continue
            rel = Path(item.filename[len(prefix):])
            if rel.is_absolute() or '..' in rel.parts or ':' in str(rel):
                raise ValueError('Unsafe archive entry: ' + str(rel))
            path = dest/rel
            path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as src, path.open('wb') as out:
                shutil.copyfileobj(src, out)


def build(cache, output, llvm_runtime=None):
    fetch(cache)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nexys-package-') as temp:
        stage = Path(temp)/'Nexys-Lab'
        stage.mkdir()
        for name in ('server.py', 'live.py', 'board.py', 'vivado.py', 'ghdl_backend.py',
                     'windows_performance.py', 'desktop.py', 'README.md', 'Start-Nexys-Lab.cmd',
                     'Start-Nexys-Lab-App.cmd', 'Start-Nexys-Lab-Compatible.cmd'):
            shutil.copy2(ROOT/name, stage/name)
        for path in ROOT.glob('test_*.py'):
            shutil.copy2(path,stage/path.name)
        for name in ('web', 'examples', 'third_party', 'docs'):
            shutil.copytree(ROOT/name, stage/name)
        extract(cache/'ghdl.zip', stage/'runtime/ghdl')
        if llvm_runtime is not None:
            if not (llvm_runtime/'READY').is_file() or not (llvm_runtime/'ucrt64/bin/ghdl.exe').is_file():
                raise ValueError('Supply a validated LLVM runtime directory containing READY and ucrt64/bin/ghdl.exe')
            shutil.copytree(llvm_runtime, stage/'runtime/ghdl-llvm')
        extract(cache/'python.nupkg', stage/'runtime/python', prefix='tools/')
        shutil.copy2(cache/'ghdl-source.tar.gz', stage/'third_party/ghdl-6.0.0-source.tar.gz')
        (stage/'third_party/downloads.json').write_text(json.dumps(ASSETS, indent=2))
        (stage/'START-HERE.txt').write_text(
            'NEXYS LAB - WINDOWS x64 PORTABLE\n\n'
            '1. Extract the entire ZIP to a regular writable folder. Do not run inside the ZIP.\n'
            '2. Double-click Start-Nexys-Lab.cmd. Your browser opens automatically.\n'
            '   Or use Start-Nexys-Lab-App.cmd for a separate Edge app window.\n'
            '3. Keep the console window open. Press Ctrl+C there to stop.\n\n'
            'Python 3.13.7 and GHDL 6.0.0 are included. No installation, admin access,\n'
            'PATH changes, or Internet connection are needed to run this package.\n'
            'Supported target: Windows 10/11 x64 (Intel/AMD).\n'
            'The launcher uses a free port automatically if port 8000 is occupied.\n'
            'Use the browser tab opened by the launcher, not an old bookmark.\n'
            'See README.md and third_party for usage, limitations and license notices.\n', encoding='utf-8')
        package = output/'Nexys-Lab-Windows-x64.zip'
        with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    z.write(path, path.relative_to(stage.parent))
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        (output/(package.name+'.sha256')).write_text(digest+'  '+package.name+'\n')
        print('Built', package, 'SHA256', digest, flush=True)
        return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=ROOT/'.local/downloads')
    parser.add_argument('--output', type=Path, default=ROOT/'dist')
    parser.add_argument('--llvm-runtime', type=Path, help='Optional validated native LLVM runtime to bundle alongside mcode')
    args = parser.parse_args()
    build(args.cache.resolve(), args.output.resolve(), args.llvm_runtime.resolve() if args.llvm_runtime else None)
