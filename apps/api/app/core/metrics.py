"""Small dependency-free runtime metrics for the private beta deployment."""

from collections import defaultdict
from threading import Lock


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._in_flight = 0
        self._requests: defaultdict[tuple[str, str], int] = defaultdict(int)
        self._duration_seconds = 0.0

    def begin_request(self) -> None:
        with self._lock:
            self._in_flight += 1

    def observe_request(self, method: str, status_code: int, duration_seconds: float) -> None:
        status_class = f"{status_code // 100}xx"
        with self._lock:
            self._in_flight = max(self._in_flight - 1, 0)
            self._requests[(method, status_class)] += 1
            self._duration_seconds += duration_seconds

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP cocoon_http_requests_total HTTP responses returned by Cocoon.",
                "# TYPE cocoon_http_requests_total counter",
            ]
            for (method, status_class), count in sorted(self._requests.items()):
                labels = f'method="{method}",status_class="{status_class}"'
                lines.append(
                    f"cocoon_http_requests_total{{{labels}}} {count}"
                )
            lines.extend(
                [
                    "# HELP cocoon_http_request_duration_seconds_total Total HTTP handling time.",
                    "# TYPE cocoon_http_request_duration_seconds_total counter",
                    f"cocoon_http_request_duration_seconds_total {self._duration_seconds:.6f}",
                    "# HELP cocoon_http_requests_in_flight HTTP requests currently being handled.",
                    "# TYPE cocoon_http_requests_in_flight gauge",
                    f"cocoon_http_requests_in_flight {self._in_flight}",
                ]
            )
            return "\n".join(lines) + "\n"
