"""The exceptions code raises on purpose, which are the core's (`omni_bench_core.errors`):

    SystemFailed       the system failed on one page, which fails; raised on purpose. `SystemTimeout`,
                       `SystemUnreachable` and `Unreadable` are its kinds
    Unscored           a scorer couldn't score a page (a judge that didn't answer): raised from `score`, or
                       returned in the page's place from `score_all`; the page waits for a later grading

Everything else a user meets is a native exception, raised as it is with its traceback: a `ValueError` for
what was asked wrong (a flag, an option, a dataset, a manifest, a gold, a missing key, a run graded before it
is finished), a `PermissionError` for an account that can't pay, an `ImportError` for a missing package, and
a refused connection as the connection error it is, with a note saying how to start the server. A bug is
raised as it is, with a note naming the class and the page. `counted` writes a count in a message.
"""
from omni_bench_core.errors import (
    SystemFailed,
    SystemTimeout,
    SystemUnreachable,
    Unreadable,
    Unscored,
    counted,
)

__all__ = ["SystemFailed", "SystemTimeout", "SystemUnreachable", "Unreadable", "Unscored", "counted"]
