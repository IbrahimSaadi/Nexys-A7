# Bundled software

The Windows portable distribution contains unmodified upstream binaries:

- **GHDL 6.0.0**, UCRT64 standalone mcode backend, from https://github.com/ghdl/ghdl/releases/tag/v6.0.0. GHDL is licensed under GPL v2 or later. Its complete upstream source archive is included as `ghdl-6.0.0-source.tar.gz`; see its COPYING file and per-file notices. IEEE library notices remain with the installed library sources.
- GHDL's upstream Windows archive includes GCC's `libgcc_s_seh-1.dll` (GPL v3 with GCC Runtime Library Exception), mingw-w64's `libwinpthread-1.dll` (permissive licenses), and `zlib1.dll` (zlib license). Their license texts are included in this directory. Source projects: https://gcc.gnu.org/ (GCC runtime), https://www.mingw-w64.org/ (winpthreads), https://zlib.net/ (zlib).
- **CPython 3.13.7** for Windows x64, official `python` NuGet package from https://www.nuget.org/packages/python/3.13.7. Its license and incorporated third-party notices are in `runtime/python/LICENSE.txt`. Source: https://github.com/python/cpython/tree/v3.13.7.

Exact download URLs and pinned integrity hashes are recorded in `downloads.json` in the portable archive and `scripts/build_windows.py` in the project. The portable build does not modify these upstream binaries. Their inclusion does not imply endorsement by Python, GHDL, Xilinx/AMD, or Digilent.
