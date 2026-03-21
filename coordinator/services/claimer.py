"""
Claimer: atomic claim/release of entry points.
Prevents two agents from picking the same function.
"""

import time
import threading


class Claim:
    def __init__(self, func_name: str, module: str, timestamp: float):
        self.func_name = func_name
        self.module = module
        self.timestamp = timestamp


class Claimer:
    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        self._claims: dict[str, Claim] = {}  # key: "module:func_name"
        self._lock = threading.Lock()

    def _key(self, module: str, func_name: str) -> str:
        return f"{module}:{func_name}"

    def _expire_stale(self):
        now = time.time()
        expired = [k for k, c in self._claims.items()
                   if now - c.timestamp > self.ttl]
        for k in expired:
            del self._claims[k]

    def claim(self, module: str, func_name: str) -> bool:
        with self._lock:
            self._expire_stale()
            key = self._key(module, func_name)
            if key in self._claims:
                return False
            self._claims[key] = Claim(func_name, module, time.time())
            return True

    def release(self, module: str, func_name: str) -> bool:
        with self._lock:
            key = self._key(module, func_name)
            if key in self._claims:
                del self._claims[key]
                return True
            return False

    def is_claimed(self, module: str, func_name: str) -> bool:
        with self._lock:
            self._expire_stale()
            return self._key(module, func_name) in self._claims

    def claimed_count(self, module: str) -> int:
        with self._lock:
            self._expire_stale()
            return sum(1 for c in self._claims.values() if c.module == module)

    def list_claims(self, module: str) -> list[str]:
        with self._lock:
            self._expire_stale()
            return [c.func_name for c in self._claims.values()
                    if c.module == module]
