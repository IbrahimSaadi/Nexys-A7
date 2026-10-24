"""Record installed runtime provenance and retain supplied package licenses."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    'ghdl-llvm-6.0.0': 'https://github.com/ghdl/ghdl/releases/download/v6.0.0/mingw-w64-ucrt-x86_64-ghdl-llvm-6.0.0-1-any.pkg.tar.zst',
    **{short: 'https://repo.msys2.org/mingw/ucrt64/mingw-w64-ucrt-x86_64-' + full + '-any.pkg.tar.zst'
       for short, full in [('gcc-15.2.0-13', 'gcc-15.2.0-13'), ('gcc-ada-15.2.0-13', 'gcc-ada-15.2.0-13'),
                           ('gcc-libs-15.2.0-13', 'gcc-libs-15.2.0-13'), ('binutils-2.46-2', 'binutils-2.46-2'),
                           ('crt-13', 'crt-13.0.0.r560.g3197fc7d6-1'),
                           ('winpthreads-13', 'winpthreads-13.0.0.r560.g3197fc7d6-1'),
                           ('zlib-1.3.2-2', 'zlib-1.3.2-2'), ('zstd-1.5.7-2', 'zstd-1.5.7-2'),
                           ('gettext-runtime-1.0-1', 'gettext-runtime-1.0-1'),
                           ('libiconv-1.18-1', 'libiconv-1.18-1'),
                           ('windows-default-manifest-6.4-4', 'windows-default-manifest-6.4-4')]},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    records = []
    licenses = ROOT/'third_party/llvm-packages'
    for short, url in PACKAGES.items():
        archive = ROOT/'runtime/downloads'/(short + '.tar.zst')
        records.append({'archive': str(archive.relative_to(ROOT)), 'url': url,
                        'sha256': sha(archive), 'bytes': archive.stat().st_size})
        names = subprocess.check_output(['tar', '-tf', str(archive)], text=True).splitlines()
        for name in names:
            if name == '.PKGINFO' or ('/share/licenses/' in name and not name.endswith('/')):
                relative = PurePosixPath(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unexpected archive member')
                destination = licenses/short/relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(subprocess.check_output(['tar', '-xOf', str(archive), name]))
    assert records[0]['sha256'] == 'e5549cb7e5a6e00a3b48f25f776b248407f2f4702a051487281aa7226393ccd2'
    prefix = ROOT/'runtime/ghdl-llvm/ucrt64'
    libraries = []
    for name in ('std_logic_1164-body', 'numeric_std-body'):
        source = prefix/'lib/ghdl/src/ieee2008'/(name + '.vhdl')
        original = ROOT/'runtime/ghdl/lib/ghdl/src/ieee2008'/(name + '.vhdl')
        assert sha(source) == sha(original), 'IEEE source differs from original engine'
        libraries.append({'source': str(source.relative_to(ROOT)), 'source_sha256': sha(source),
                          'object_sha256': sha(prefix/'lib/ghdl/ieee/v08'/(name + '.o')), 'optimization': '-O3'})
    artifact = {'packages': records, 'optimized_ieee': libraries, 'project_optimization': '-O2',
                'copied_from_original_bundle': [{ 'file': str(path.relative_to(ROOT)), 'sha256': sha(path)}
                    for path in (ROOT/'runtime/ghdl/bin').glob('*.dll')],
                'note': 'GHDL archive checked against GitHub release digest. MSYS2 package hashes recorded after HTTPS download.'}
    (ROOT/'third_party/llvm-runtime.json').write_text(json.dumps(artifact, indent=2), encoding='utf-8')
    print('Recorded', len(records), 'packages; IEEE source hashes match original bundle.')
