"""
Service Health Monitor
=====================
Thread-safe health checking for all backend services.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests


class ServiceHealth:
    """Tracks live availability of registered endpoints."""

    def __init__(self):
        self._lock = threading.Lock()
        self._endpoints: dict[str, tuple[str, dict[str, str]]] = {}
        self._status: dict[str, bool] = {}

    def register(
        self, name: str, health_url: str, headers: Optional[dict] = None
    ) -> "ServiceHealth":
        """Register a service endpoint for health checking. Returns self for chaining."""
        with self._lock:
            self._endpoints[name] = (health_url, headers or {})
            self._status[name] = False
        return self

    def refresh(self) -> dict[str, bool]:
        """Probe all registered endpoints. Returns {name: is_up}."""

        def _probe(name: str, url: str, headers: dict) -> tuple[str, bool]:
            try:
                r = requests.get(url, headers=headers, timeout=(2, 5))
                return name, r.status_code < 400
            except Exception:
                return name, False

        result = {}
        with ThreadPoolExecutor(max_workers=max(len(self._endpoints), 1)) as pool:
            futs = [
                pool.submit(_probe, name, url, hdrs)
                for name, (url, hdrs) in self._endpoints.items()
            ]
            for f in as_completed(futs, timeout=10):
                try:
                    n, ok = f.result()
                    result[n] = ok
                except Exception:
                    pass

        with self._lock:
            self._status.update(result)
        return dict(self._status)

    def is_up(self, service: str) -> bool:
        with self._lock:
            return self._status.get(service, False)

    def get_all(self) -> dict[str, bool]:
        with self._lock:
            return dict(self._status)
