"""
Resolver: handles resolving functions and updating coverage.
All writes go through the write queue.
"""

from services.registry import Registry
from services.write_queue import WriteQueue, WriteOp


class Resolver:
    def __init__(self, registry: Registry, write_queue: WriteQueue):
        self.registry = registry
        self.wq = write_queue

    def resolve_func(self, module: str, func_name: str,
                     contour: str, role: str = "helper") -> bool:
        mod = self.registry.get_module(module)
        if mod is None:
            return False

        node = mod.get_coverage_node(func_name)
        if node is None:
            return False

        def _do_resolve():
            node["status"] = "resolved"
            if contour not in node.get("partof", []):
                node.setdefault("partof", []).append(contour)

        self.wq.enqueue(WriteOp(
            module=module,
            op_type="resolve",
            func_name=func_name,
            action=_do_resolve,
        ))
        return True

    def resolve_micro(self, module: str, func_name: str,
                      contour: str) -> bool:
        """Mark micro as used by contour but keep status uncovered
        unless code was improved."""
        mod = self.registry.get_module(module)
        if mod is None:
            return False

        node = mod.get_coverage_node(func_name)
        if node is None:
            return False

        def _do_resolve_micro():
            if contour not in node.get("partof", []):
                node.setdefault("partof", []).append(contour)

        self.wq.enqueue(WriteOp(
            module=module,
            op_type="resolve_micro",
            func_name=func_name,
            action=_do_resolve_micro,
        ))
        return True

    def update_func_code(self, module: str, func_name: str,
                         code: str) -> bool:
        mod = self.registry.get_module(module)
        if mod is None:
            return False

        def _do_write():
            from storage.func_io import write_resolved
            write_resolved(mod.path, func_name, code)

        self.wq.enqueue(WriteOp(
            module=module,
            op_type="write_code",
            func_name=func_name,
            action=_do_write,
        ))
        return True
