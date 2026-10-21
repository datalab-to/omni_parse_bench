"""One page's share of the clock: the core's `Budget`, with `timeout` for one request, and `PollRetry`."""
from __future__ import annotations

from omni_bench_core import adapter

PollRetry = adapter.PollRetry


class Budget(adapter.Budget):
    """The core's per-page deadline, with a timeout for one request."""

    __slots__ = ()

    def timeout(self, cap: float) -> float:
        """One HTTP request's timeout: `cap`, cut to what is left, and at least 1 s so a request is made."""
        return min(cap, max(1.0, self.remaining()))
