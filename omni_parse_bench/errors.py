"""The errors a user meets, which are the core's (`omni_bench_core.errors`), so the `opb` command tells them
from our bugs:

    UsageError         what was asked is wrong: a bad flag, option, dataset, manifest or gold; fix it and ask
                       again. `Unfinished` is one: grading a run before every page has an answer
    Stop               a run can't go on: an account that can't pay, a missing key or dependency, a model
                       server that isn't running, or a bug in an adapter; fix it and run the same command
                       again
    MissingCredential  the Stop of a missing key

Anything else raised is a bug of ours. `counted` writes a count in a message.
"""
from omni_bench_core.errors import MissingCredential, Stop, Unfinished, UsageError, counted

__all__ = ["MissingCredential", "Stop", "Unfinished", "UsageError", "counted"]
