import threading
import time

import pytest

from pulsemetrics import ipc
from pulsemetrics.windows import lock_runtime


def test_named_pipe_round_trip_and_single_instance(tmp_path):
    server = ipc.Server(lambda c: {"id": c["id"], "ok": True, "result": c["args"]})
    stop = threading.Event()
    def serve():
        while not stop.is_set():
            server.once()
    thread = threading.Thread(target=serve)
    thread.start()
    try:
        for _ in range(3):
            assert ipc.request("status", {"text": "λ 🚀", "number": 12}, name=server.name) == {"text": "λ 🚀", "number": 12}
        with pytest.raises(OSError):
            ipc.create_pipe(server.name)
        lock = lock_runtime(tmp_path / "application.lock")
        try:
            with pytest.raises(RuntimeError):
                lock_runtime(tmp_path / "application.lock")
        finally:
            ipc.close(lock)
    finally:
        stop.set()
        thread.join(timeout=8)
        server.close()
    assert not thread.is_alive()


def test_job_closure_reaps_owned_process():
    import subprocess
    import sys
    from pulsemetrics.windows import Job
    job = Job()
    child = subprocess.Popen([sys.executable, "-c", "import time;print('ready',flush=True);time.sleep(60);print('normal completion')"], stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        job.own(child)
        assert child.stdout.readline().strip() == b"ready"
        assert child.poll() is None
        job.close()
        child.wait(timeout=5)  # Windows may report 0 for KILL_ON_JOB_CLOSE.
        assert child.stdout.read() == b""  # the 60-second task never completed normally
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()
