"""Owned native subprocess with bounded request acknowledgements and drained pipes."""
import json
import queue
import subprocess
import threading
import uuid


class Child:
    def __init__(self, command, env, job, logger, events=None):
        self.logger, self.events = logger, events
        self.pending = {}
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.final = None
        self.failure = None
        self.ready_received = False
        self.process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        job.own(self.process)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._errors, daemon=True).start()

    def _read(self):
        try:
            while line := self.process.stdout.readline(65537):
                if len(line.encode("utf-8")) > 65536 or not line.endswith("\n"):
                    raise ValueError("Native protocol record exceeds limit")
                message = json.loads(line)
                if "id" in message:
                    with self.lock:
                        pending = self.pending.get(message["id"])
                        if pending:
                            pending.put_nowait(message)
                elif message.get("event") == "ready":
                    self.ready_received = True
                    self.ready.set()
                elif message.get("event") == "stopped":
                    self.final = message
                    self.stopped.set()
                elif self.events:
                    self.events(message)
        except (OSError, ValueError, queue.Full) as exc:
            self.failure = str(exc)
            self.logger.error("Native protocol failure: %s", exc)
        finally:
            self.ready.set()

    def _errors(self):
        while line := self.process.stderr.readline(4096):
            self.logger.warning("%s", line.rstrip())

    def wait_ready(self):
        if not self.ready.wait(10) or not self.ready_received or self.failure or self.process.poll() is not None:
            raise RuntimeError("Native component did not become ready; inspect component log")

    def request(self, op, args=None, request_id=None, timeout=4):
        rid = request_id or str(uuid.uuid4())
        message = json.dumps({"v": 1, "id": rid, "op": op, "args": args or {}}, allow_nan=False)
        if len(message.encode("utf-8")) >= 65535:
            raise ValueError("Native command exceeds limit")
        result = queue.Queue(maxsize=1)
        with self.lock:
            if len(self.pending) >= 64 or rid in self.pending:
                raise RuntimeError("Native command queue is busy")
            self.pending[rid] = result
            try:
                self.process.stdin.write(message + "\n")
                self.process.stdin.flush()
            except Exception:
                self.pending.pop(rid, None)
                raise
        try:
            reply = result.get(timeout=timeout)
            if not reply.get("ok"):
                raise RuntimeError(reply.get("message", "Native command rejected"))
            return reply.get("result", {})
        except queue.Empty as exc:
            raise TimeoutError("Native acknowledgement timed out; outcome may be unknown") from exc
        finally:
            with self.lock:
                self.pending.pop(rid, None)

    def stop(self, timeout=14):
        if self.process.poll() is None:
            self.request("stop", timeout=2)
            if not self.stopped.wait(timeout):
                raise TimeoutError("Native shutdown did not complete")
            self.process.wait(timeout=2)
        if self.process.returncode != 0 or not self.final or not self.final.get("clean"):
            raise RuntimeError(f"Native shutdown was not clean: {self.final or self.failure}")

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()
