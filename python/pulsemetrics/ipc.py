"""One bounded JSON named pipe. Current-user ACL; local clients only; no pickle."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
import struct
import time
import uuid

K = C.WinDLL("kernel32", use_last_error=True)
A = C.WinDLL("advapi32", use_last_error=True)
INVALID = C.c_void_p(-1).value
LIMIT = 65536


def api(dll, name, restype, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, args
    return fn


close = api(K, "CloseHandle", W.BOOL, W.HANDLE)
create_file = api(K, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE)
read_file = api(K, "ReadFile", W.BOOL, W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p)
write_file = api(K, "WriteFile", W.BOOL, W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p)
connect = api(K, "ConnectNamedPipe", W.BOOL, W.HANDLE, C.c_void_p)
disconnect = api(K, "DisconnectNamedPipe", W.BOOL, W.HANDLE)
set_mode = api(K, "SetNamedPipeHandleState", W.BOOL, W.HANDLE, C.POINTER(W.DWORD), C.c_void_p, C.c_void_p)
local_free = api(K, "LocalFree", C.c_void_p, C.c_void_p)


class Security(C.Structure):
    _fields_ = [("size", W.DWORD), ("descriptor", C.c_void_p), ("inherit", W.BOOL)]


def user_sid():
    token = W.HANDLE()
    get_process = api(K, "GetCurrentProcess", W.HANDLE)
    open_token = api(A, "OpenProcessToken", W.BOOL, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE))
    info = api(A, "GetTokenInformation", W.BOOL, W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD))
    sid_text = api(A, "ConvertSidToStringSidW", W.BOOL, C.c_void_p, C.POINTER(C.c_void_p))
    if not open_token(get_process(), 8, C.byref(token)):
        raise C.WinError(C.get_last_error())
    try:
        size = W.DWORD()
        info(token, 1, None, 0, C.byref(size))
        buffer = C.create_string_buffer(size.value)
        if not info(token, 1, buffer, size, C.byref(size)):
            raise C.WinError(C.get_last_error())
        text = C.c_void_p()
        sid = C.cast(buffer, C.POINTER(C.c_void_p))[0]
        if not sid_text(sid, C.byref(text)):
            raise C.WinError(C.get_last_error())
        try:
            return C.wstring_at(text)
        finally:
            local_free(text)
    finally:
        close(token)


def create_pipe(name):
    descriptor = C.c_void_p()
    convert = api(A, "ConvertStringSecurityDescriptorToSecurityDescriptorW", W.BOOL, W.LPCWSTR, W.DWORD, C.POINTER(C.c_void_p), C.c_void_p)
    if not convert(f"D:P(A;;GA;;;{user_sid()})", 1, C.byref(descriptor), None):
        raise C.WinError(C.get_last_error())
    try:
        security = Security(C.sizeof(Security), descriptor, False)
        create = api(K, "CreateNamedPipeW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, C.POINTER(Security))
        # Duplex, first-instance; byte stream, nonblocking, reject remote clients.
        handle = create(name, 3 | 0x80000, 1 | 8, 1, LIMIT + 4, LIMIT + 4, 1000, C.byref(security))
        if handle == INVALID:
            raise C.WinError(C.get_last_error())
        return handle
    finally:
        local_free(descriptor)


def transfer(handle, payload=None, size=None, deadline=None):
    deadline = deadline or time.monotonic() + 5
    result = bytearray()
    count = len(payload) if payload is not None else size
    offset = 0
    while offset < count:
        if time.monotonic() > deadline:
            raise TimeoutError("Local control pipe timed out; outcome may be unknown")
        done = W.DWORD()
        buffer = C.create_string_buffer(payload[offset:]) if payload is not None else C.create_string_buffer(count - offset)
        fn = write_file if payload is not None else read_file
        ok = fn(handle, buffer, count - offset, C.byref(done), None)
        if not ok and C.get_last_error() != 232:  # ERROR_NO_DATA in nonblocking mode
            raise C.WinError(C.get_last_error())
        if done.value:
            if payload is None:
                result.extend(buffer.raw[:done.value])
            offset += done.value
        else:
            time.sleep(0.01)
    return bytes(result)


def send(handle, message, deadline):
    raw = json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(raw) <= LIMIT:
        raise ValueError("Control record exceeds 64 KiB")
    transfer(handle, payload=struct.pack("<I", len(raw)) + raw, deadline=deadline)


def receive(handle, deadline):
    size = struct.unpack("<I", transfer(handle, size=4, deadline=deadline))[0]
    if not 0 < size <= LIMIT:
        raise ValueError("Invalid control frame length")
    value = json.loads(transfer(handle, size=size, deadline=deadline))
    if not isinstance(value, dict):
        raise ValueError("Expected a control object")
    return value


def request(op, args=None, *, name=None, request_id=None, timeout=6):
    name = name or os.environ.get("PULSE_PIPE")
    if not name:
        raise ConnectionError("Launch PulseMetrics with scripts/launch.py")
    deadline = time.monotonic() + timeout
    while True:
        handle = create_file(name, 0xC0000000, 0, None, 3, 0, None)
        if handle != INVALID:
            break
        if time.monotonic() >= deadline:
            raise ConnectionError("PulseMetrics controller is unavailable")
        time.sleep(0.03)
    try:
        mode = W.DWORD(1)
        if not set_mode(handle, C.byref(mode), None, None):
            raise C.WinError(C.get_last_error())
        rid = request_id or str(uuid.uuid4())
        send(handle, {"v": 1, "id": rid, "op": op, "args": args or {}}, deadline)
        reply = receive(handle, deadline)
        transfer(handle, payload=b"\x01", deadline=deadline)
        if reply.get("id") != rid:
            raise ValueError("Mismatched control acknowledgement")
        if not reply.get("ok"):
            raise RuntimeError(reply.get("message", "Command failed"))
        return reply.get("result", {})
    finally:
        close(handle)


class Server:
    def __init__(self, handler):
        self.name = rf"\\.\pipe\PulseMetricsV2-{uuid.uuid4()}"
        self.handle = create_pipe(self.name)
        self.handler = handler

    def once(self):
        connected = connect(self.handle, None)
        code = C.get_last_error()
        if not connected and code not in (535,):  # ERROR_PIPE_CONNECTED
            if code in (536, 232):
                time.sleep(0.02)
                return
            raise C.WinError(code)
        try:
            deadline = time.monotonic() + 6
            command = receive(self.handle, deadline)
            response = self.handler(command)
            send(self.handle, response, deadline)
            transfer(self.handle, size=1, deadline=deadline)
        except (OSError, ValueError, TimeoutError):
            pass  # disconnected/malformed client cannot stop the application
        finally:
            disconnect(self.handle)

    def close(self):
        close(self.handle)
