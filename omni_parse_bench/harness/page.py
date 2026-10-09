"""One page, one vendor, under the rules that make a comparison fair.

    predict(provider, page, wants=None) -> record

The uniform rules:

- one timeout per call for every provider, the same for each of a page's calls (`budget.py`);
- maximum tier for every provider: each adapter's `Config` defaults are its top settings;
- each wanted output is asked for; one a vendor can't produce is recorded as unsupported, and the
  scorer leaves its tests out rather than failing them;
- transient failures (429, 5xx) retry, real answers (a 400) do not; and
- account-level failures (a 402, a credit ceiling) raise `AccountFailure` and stop the run.

A record:

    outputs     output type -> its value; absent when unsupported, None when its call failed
    errors      output type -> "unsupported", or why its call failed
    calls       one per call made: the outputs it produced, what was sent, cost, time, attempts, the
                timeout it ran under, and its failure (class, status, transient)
    raw         each call's response as received, for re-parsing without paying again
    provider, settings, timeout_s, captured_at
"""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

import httpx

from . import budget, contract, errors, registry

TRANSIENT_ATTEMPTS = 4
TRANSIENT_BACKOFF = (20, 60, 120)
ACCOUNT_MARKERS = ("exceeded the maximum number of credits", "subscription has expired",
                   "insufficient_quota", "insufficient credits")
# A 403 that refuses this page's content, not the account (OpenRouter's moderation flag).
PAGE_REFUSALS = ("moderation", "flagged")

# Note: bound here, not called as `registry.adapter`, so a test can substitute the vendor call
# on this module while `registry.config_for` keeps building the real `Config`.
adapter = registry.adapter


def _is_account_failure(exc: errors.VendorError) -> bool:
    """A key the vendor refuses (401, 403) or an account that can't pay (402, or a marker): the same
    on every page, so it stops the run rather than failing pages. A 403 for this page's content (a
    moderation flag) is about the page, not the account. Markers are read in the vendor's error, not
    in a whole answer, which can hold the page's own text."""
    body = (exc.body or "") if (exc.status or 0) >= 400 else ""
    message = f"{exc} {body}".lower()
    if exc.status == 403 and any(m in message for m in PAGE_REFUSALS): return False
    return exc.status in (401, 402, 403) or any(m in message for m in ACCOUNT_MARKERS)


def _call(api: contract.Adapter, page: Path, request: contract.Request, timeout: float,
          config: Any) -> contract.Call:
    """`api.call`, with a network fault made a `VendorUnreachable` and an answer the adapter couldn't
    read (bad JSON, a missing field) a `VendorError`, the same way for every adapter."""
    try:
        return api.call(page, request, timeout=timeout, config=config)
    except httpx.TransportError as exc:
        raise errors.VendorUnreachable(f"{type(exc).__name__}: {exc}"[:300]) from None
    # Note: about this page's answer, not the run, so recorded rather than raised; not transient,
    # since the same answer would fail the same way.
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise errors.VendorError(f"no readable answer: {type(exc).__name__}: {exc}"[:300]) from None


def _parse(api: contract.Adapter, got: contract.Call, request: contract.Request,
           config: Any) -> tuple[dict, dict]:
    """`api.parse` on an answer, its outputs and why any is missing. A parser that fails fails only
    this answer's outputs, which the saved answer can rebuild after a fix (`opb reparse`)."""
    try:
        return api.parse(got.raw, request, config)
    except (errors.VendorError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        why = f"the adapter couldn't read the answer: {type(exc).__name__}: {exc}"[:300]
        return {}, dict.fromkeys(request.outputs, why)


def predict(provider: str, page: str | Path, wants: set[str] | frozenset[str] | None = None, *,
            timeout: float = registry.DEFAULT_TIMEOUT, **options: Any) -> dict:
    """Run one page through one provider and return its outputs with their evidence.

    `wants` are the output types to produce, by default every one the provider supports.
    A `VendorError` is recorded against the outputs of its call; `AccountFailure`,
    `MissingCredential` and `MissingDependency` are raised, since they are not facts about this page.
    """
    api = adapter(provider)
    page = Path(page)
    if not page.exists():
        raise FileNotFoundError(f"no page at {page}")
    wants = frozenset(api.SUPPORTS if wants is None else wants)
    config = registry.config_for(provider, options)
    outputs: dict[str, Any] = {}
    errs = {o: "unsupported" for o in sorted(wants - api.SUPPORTS)}
    calls, raw = [], []
    for request in api.requests(wants & api.SUPPORTS, config):
        # Note: each call has the whole budget, so a vendor whose outputs take several calls isn't
        # held to less time per call than one that makes a single call.
        clock = budget.Budget(timeout)
        started, got, error, attempts, spent = time.time(), None, None, 0, []
        for attempt in range(TRANSIENT_ATTEMPTS):
            attempts = attempt + 1
            try:
                got = _call(api, page, request, clock.remaining(), config)
                error = None
                break
            except errors.VendorError as exc:
                if _is_account_failure(exc):
                    raise errors.AccountFailure(str(exc)[:200]) from None
                error = exc
                if exc.cost is not None: spent.append(exc.cost)
                if not exc.transient or attempt == TRANSIENT_ATTEMPTS - 1: break
                wait = TRANSIENT_BACKOFF[min(attempt, len(TRANSIENT_BACKOFF) - 1)]
                time.sleep(min(wait, clock.remaining()))
                if clock.expired():
                    error = errors.VendorTimeout(f"the uniform {timeout:.0f}s budget was spent over "
                                                 f"{attempts} attempt(s); last failure: {exc}"[:400],
                                                 raw=exc.raw, job_id=exc.job_id)
                    break
        if got is not None:
            spent.append(got.cost)
            parsed, why = _parse(api, got, request, config)
            for o in request.outputs:
                outputs[o] = parsed.get(o)
                if outputs[o] is None: errs[o] = why.get(o) or "the call returned no such output"
        else:
            outputs |= dict.fromkeys(request.outputs)
            errs |= dict.fromkeys(request.outputs, f"{type(error).__name__}: {error}"[:600])
        failure = None if error is None else {"class": type(error).__name__, "status": error.status,
                                              "transient": error.transient}
        calls.append({"outputs": sorted(request.outputs), "sent": request.sent,
                      **contract.total(spent)._asdict(), "wall_s": round(time.time() - started, 1),
                      "attempts": attempts, "timeout_s": timeout, "failure": failure,
                      "job_id": got.job_id if got is not None else getattr(error, "job_id", None)})
        raw.append(got.raw if got is not None else (error.raw if error.raw is not None else error.body))
    return {
        "outputs": outputs, "errors": errs, "calls": calls, "raw": raw,
        "provider": provider, "settings": dataclasses.asdict(config),
        "timeout_s": timeout, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def reparse(record: dict, add: frozenset[str] = frozenset()) -> dict:
    """`record` with its outputs read again from its saved answers by the current adapter code.

    A parsing fix then costs nothing: each call's saved answer goes through `parse` again. A call
    that got no answer (a timeout, a refused request) keeps its outputs and errors as they were.
    `add` names outputs to read from each answer as well, when the answer holds them (a vendor's one
    call answers with its typed blocks beside its html): a new test's output without a new call. An
    added output an answer doesn't hold is left as it was, not recorded as an error.
    """
    api = adapter(record["provider"])
    config = registry.config_for(record["provider"], {k: v for k, v in record["settings"].items()
                                                      if k != "model"})
    outputs, errs = dict(record["outputs"]), dict(record["errors"])
    for call, answer in zip(record["calls"], record["raw"], strict=True):
        # Note: a call that failed only in parsing (the vendor answered, 200) kept its answer, which the
        # adapter as it is now may read; an HTTP error's saved body is no answer.
        if answer is None or (call.get("failure") or {}).get("status", 200) != 200: continue
        asked = frozenset(call["outputs"])
        request = contract.Request(asked | (add & api.SUPPORTS), call["sent"])
        parsed, why = _parse(api, contract.Call(answer), request, config)
        for o in request.outputs:
            if o not in asked:
                if parsed.get(o) is not None and outputs.get(o) is None:
                    outputs[o] = parsed[o]
                    errs.pop(o, None)
                continue
            outputs[o] = parsed.get(o)
            if outputs[o] is None: errs[o] = why.get(o) or "the call returned no such output"
            else: errs.pop(o, None)
    return record | {"outputs": outputs, "errors": errs}
