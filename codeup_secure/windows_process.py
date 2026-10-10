"""Windows Job Object: attach suspended process before any plugin can spawn."""

import ctypes
from ctypes import wintypes
import threading
from .errors import CodeupError


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class BASIC_LIMITS(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class EXTENDED_LIMITS(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BASIC_LIMITS), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class THREAD_ENTRY(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Thread32First": ([wintypes.HANDLE, ctypes.POINTER(THREAD_ENTRY)], wintypes.BOOL),
            "Thread32Next": ([wintypes.HANDLE, ctypes.POINTER(THREAD_ENTRY)], wintypes.BOOL),
            "OpenThread": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise CodeupError("process_isolation_failed", "Cannot create Windows process job; CLI was not started.")
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x2000
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise CodeupError("process_isolation_failed", "Cannot configure Windows process cleanup; CLI was not started.")

    def attach_and_resume(self, child):
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, int(child._handle)):
                raise OSError()
            snapshot = self.kernel.CreateToolhelp32Snapshot(4, 0)
            if snapshot == ctypes.c_void_p(-1).value:
                raise OSError()
            resumed = False
            try:
                entry = THREAD_ENTRY()
                entry.dwSize = ctypes.sizeof(entry)
                found = self.kernel.Thread32First(snapshot, ctypes.byref(entry))
                while found:
                    if entry.th32OwnerProcessID == child.pid:
                        thread = self.kernel.OpenThread(2, False, entry.th32ThreadID)
                        if not thread:
                            raise OSError()
                        try:
                            if self.kernel.ResumeThread(thread) == 0xFFFFFFFF:
                                raise OSError()
                            resumed = True
                        finally:
                            self.kernel.CloseHandle(thread)
                        break
                    found = self.kernel.Thread32Next(snapshot, ctypes.byref(entry))
            finally:
                self.kernel.CloseHandle(snapshot)
            if not resumed:
                raise OSError()
        except OSError:
            child.kill()
            child.wait()
            self.close()
            raise OSError("Windows process job setup failed") from None

    def terminate(self):
        with self.lock:
            if self.handle:
                self.kernel.TerminateJobObject(self.handle, 1)

    def close(self):
        with self.lock:
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
