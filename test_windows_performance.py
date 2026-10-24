"""Verify the Windows QoS request against the OS, on our own child process."""
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from windows_performance import interactive_qos


class WindowsPerformanceTests(unittest.TestCase):
    def test_other_platform_keeps_default(self):
        with patch('windows_performance.os.name', 'posix'):
            self.assertFalse(interactive_qos(0))

    @unittest.skipUnless(os.name == 'nt', 'Windows API test')
    def test_child_disables_execution_speed_throttling_without_raising_priority(self):
        import ctypes
        from ctypes import wintypes
        child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'], stdin=subprocess.PIPE)
        try:
            if not interactive_qos(child.pid):
                self.skipTest('Process power throttling API unavailable on this Windows version')
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            query = kernel.GetProcessInformation
            query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            query.restype = wintypes.BOOL
            state = (wintypes.ULONG * 3)(1, 0, 0)
            self.assertTrue(query(int(child._handle), 4, state, ctypes.sizeof(state)))
            self.assertEqual(state[1] & 1, 1)
            self.assertEqual(state[2] & 1, 0)
            priority = kernel.GetPriorityClass
            priority.argtypes = [wintypes.HANDLE]
            priority.restype = wintypes.DWORD
            self.assertEqual(priority(int(child._handle)), 0x20)  # NORMAL_PRIORITY_CLASS
        finally:
            child.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
