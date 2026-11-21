"""Small Win32 process ownership and single-instance helpers."""
import ctypes as C
from ctypes import wintypes as W
import socket
import struct

from .ipc import K, INVALID, api, close, create_file


class BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_longlong), ("job_time", C.c_longlong), ("flags", W.DWORD),
                ("min_working_set", C.c_size_t), ("max_working_set", C.c_size_t),
                ("active_processes", W.DWORD), ("affinity", C.c_size_t),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", BasicLimits), ("io", C.c_ulonglong * 6),
                ("process_memory", C.c_size_t), ("job_memory", C.c_size_t),
                ("peak_process_memory", C.c_size_t), ("peak_job_memory", C.c_size_t)]


class Job:
    def __init__(self):
        self.handle = api(K, "CreateJobObjectW", W.HANDLE, C.c_void_p, W.LPCWSTR)(None, None)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE, including controller crash
        set_limits = api(K, "SetInformationJobObject", W.BOOL, W.HANDLE, C.c_int, C.c_void_p, W.DWORD)
        if not set_limits(self.handle, 9, C.byref(limits), C.sizeof(limits)):
            close(self.handle)
            raise C.WinError(C.get_last_error())

    def own(self, process):
        assign = api(K, "AssignProcessToJobObject", W.BOOL, W.HANDLE, W.HANDLE)
        if not assign(self.handle, W.HANDLE(int(process._handle))):
            process.kill()
            process.wait(timeout=5)
            raise C.WinError(C.get_last_error())

    def close(self):
        close(self.handle)


def lock_runtime(path):
    handle = create_file(str(path), 0xC0000000, 0, None, 4, 0x80, None)
    if handle == INVALID:
        raise RuntimeError("This data directory is already in use or is not writable")
    return handle


def owns_listener(pid, port, job_handle=None):
    """Return true only when the loopback listener belongs to this process or its Job."""
    library = C.WinDLL("iphlpapi", use_last_error=True)
    get_table = api(library, "GetExtendedTcpTable", W.DWORD, C.c_void_p, C.POINTER(W.DWORD), W.BOOL, W.ULONG, C.c_int, W.ULONG)
    size = W.DWORD()
    result = get_table(None, C.byref(size), False, 2, 3, 0)
    if size.value == 0:
        return False
    buffer = C.create_string_buffer(size.value)
    result = get_table(buffer, C.byref(size), False, 2, 3, 0)
    if result:
        return False

    open_process = api(K, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
    is_process_in_job = api(K, "IsProcessInJob", W.BOOL, W.HANDLE, W.HANDLE, C.POINTER(W.BOOL))
    query_limited_information = 0x1000

    raw = buffer.raw
    count = struct.unpack_from("<I", raw)[0]
    for index in range(count):
        _, address, local_port, _, _, owner = struct.unpack_from("<6I", raw, 4 + index * 24)
        if socket.ntohs(local_port & 0xFFFF) != port or address != 0x0100007F:
            continue
        if owner == pid:
            return True
        if job_handle is None:
            continue

        process = open_process(query_limited_information, False, owner)
        if not process:
            continue
        try:
            belongs = W.BOOL(False)
            if is_process_in_job(process, job_handle, C.byref(belongs)) and belongs.value:
                return True
        finally:
            close(process)
    return False
