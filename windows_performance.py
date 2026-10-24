"""Keep an interactive simulator out of Windows' background power throttling.

This is a process-local QoS request, not a change to system power plans, CPU
affinity, priority class, or HDL timing. Unsupported platforms keep defaults.
https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation
"""
import os


def interactive_qos(pid):
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes

    class PowerThrottling(ctypes.Structure):
        _fields_ = [('Version', wintypes.ULONG), ('ControlMask', wintypes.ULONG),
                    ('StateMask', wintypes.ULONG)]

    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        open_process = kernel.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        set_information = kernel.SetProcessInformation
        set_information.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        set_information.restype = wintypes.BOOL
        close_handle = kernel.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        handle = open_process(0x0200, False, pid)  # PROCESS_SET_INFORMATION
        if not handle:
            return False
        try:
            # Version 1; control EXECUTION_SPEED (1), explicitly leave it off.
            state = PowerThrottling(1, 1, 0)
            return bool(set_information(handle, 4, ctypes.byref(state), ctypes.sizeof(state)))
        finally:
            close_handle(handle)
    except (AttributeError, OSError):
        return False
