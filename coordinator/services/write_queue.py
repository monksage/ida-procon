"""
WriteQueue: sequential disk writer.
All mutations to coverage.json and files go through here.
A background worker thread processes operations one by one.
"""

import threading
import queue
from dataclasses import dataclass, field
from typing import Callable

from storage.coverage_io import save_coverage


@dataclass
class WriteOp:
    module: str
    op_type: str  # resolve | resolve_micro | write_code | submit_contour
    func_name: str = ""
    action: Callable = field(default=lambda: None)


class WriteQueue:
    def __init__(self):
        self._queue: queue.Queue[WriteOp | None] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._registry = None
        self._started = False
        self._pending_coverage: set[str] = set()  # modules needing flush

    def start(self, registry):
        self._registry = registry
        self._started = True
        self._worker.start()

    def enqueue(self, op: WriteOp):
        self._queue.put(op)

    def stop(self):
        self._queue.put(None)
        self._worker.join(timeout=10)

    def _run(self):
        while True:
            op = self._queue.get()
            if op is None:
                # flush remaining coverage
                self._flush_all_coverage()
                break
            try:
                op.action()
                if op.op_type in ("resolve", "resolve_micro", "submit_contour"):
                    self._pending_coverage.add(op.module)
                # flush coverage after each batch of operations
                # (check if queue is empty = batch done)
                if self._queue.empty() and self._pending_coverage:
                    self._flush_all_coverage()
            except Exception as e:
                print(f"  WriteQueue error ({op.op_type} {op.func_name}): {e}")
            finally:
                self._queue.task_done()

    def _flush_all_coverage(self):
        for module_name in self._pending_coverage:
            mod = self._registry.get_module(module_name)
            if mod:
                save_coverage(mod.path, mod.coverage)
        self._pending_coverage.clear()

    def wait_flush(self):
        """Block until all queued operations are processed."""
        self._queue.join()
