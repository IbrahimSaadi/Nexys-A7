"""Run Nexys Lab in an isolated Edge app window with a local Python backend."""
import os
from pathlib import Path
import subprocess
import threading

import server


def browser_path():
    for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / 'Microsoft/Edge/Application/msedge.exe'
            if candidate.is_file():
                return candidate
    raise RuntimeError('Microsoft Edge is required for this app-window launcher. Use Start-Nexys-Lab.cmd for your usual browser.')


def main(*, port=8765, profile=None, extra_browser_args=()):
    browser = browser_path()
    # A stable origin keeps projects in the same browser-local store on each launch.
    httpd = server.create_server('127.0.0.1', port)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    profile = Path(profile) if profile else Path(os.environ.get('LOCALAPPDATA', str(server.ROOT))) / 'NexysLab' / 'DesktopProfile'
    profile.mkdir(parents=True, exist_ok=True)
    process = None
    try:
        process = subprocess.Popen([
            str(browser), '--app=http://127.0.0.1:' + str(port),
            '--user-data-dir=' + str(profile), '--no-first-run', '--disable-background-mode',
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows',
            *extra_browser_args,
        ])
        print('Nexys Lab app window is running. Close it to stop this backend.', flush=True)
        process.wait()
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        httpd.shutdown()
        import live
        live.close_all()
        httpd.server_close()


if __name__ == '__main__':
    main()
