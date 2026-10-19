"""The errors a user meets, which are the core's (`omni_bench_core.errors`), so the `opb` command tells them
from our bugs:

    UsageError   what was asked is wrong: a bad flag, option, dataset, manifest or gold; fix it and ask again
    Stop         a run can't go on: an account that can't pay, a missing key or dependency; fix it and rerun

Anything else raised is a bug of ours. `counted` writes a count in a message.
"""
from omni_bench_core.errors import Stop, UsageError, counted

__all__ = ["Stop", "UsageError", "counted"]
