"""The two kinds of error a user meets, so a caller (the `opb` command) tells them from our bugs:

    UsageError   what was asked is wrong: a bad flag, option, dataset, manifest or gold; fix it and ask again
    Stop         a run can't go on: an account that can't pay, a missing key or dependency; fix it and rerun

Anything else raised is a bug of ours. Defined here, with nothing imported, so the command catches both
without importing the harness, which `opb score` doesn't need. `counted` words a count in a message.
"""


class UsageError(ValueError):
    """What was asked is wrong; the message says what, the offending value, and the fix."""


class Stop(Exception):
    """A run can't go on, the same for every page: not a fact about one, so raised, never recorded."""


def counted(n: int, noun: str) -> str:
    """`1 page`, `2 pages`: a count in a message, which "1 pages" would make read as a bug."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"
