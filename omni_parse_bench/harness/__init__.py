"""Producing predictions: everything that is not the scorer.

The core object is an adapter: a module in `providers/` with five names, stated by
`contract.Adapter`:

    Config      what the vendor can be asked
    SUPPORTS    the output types it can produce
    requests    (wants, config) -> [Request]: the calls that produce the wanted outputs
    call        (page, request, *, timeout, config) -> Call; raises its failures
    parse       (raw, request, config) -> (outputs, errors): what a saved answer holds

`predict` composes them for one page under uniform rules and returns the outputs with their
evidence: what each call was sent, the vendor's raw responses, the reported costs and the settings.
The evidence is kept so a parser bug is fixed by re-reading files, not by paying for every call
again.

    contract.py      `Adapter`, and the `Request`/`Call`/`Cost` it deals in
    errors.py        how a call fails, and whether a retry can fix it
    budget.py        one call's share of the clock
    layout.py        a vendor's layout blocks as the `blocks` output
    raster.py        a PDF page as an image, for vendors that take images
    registry.py      which adapter, at what settings, filed under what name
    page.py          `predict`: one page, one vendor
    providers/       one module per vendor

Orchestration (which pages, in what order, how many at once) is left to the caller;
`omni_parse_bench/benchmark.py` is one such loop. The scorer never imports this package.

    pip install 'omni-parse-bench[harness]'
"""
from __future__ import annotations

from .contract import Adapter, Call, Cost, Request
from .errors import AccountFailure, MissingCredential, MissingDependency, VendorError, VendorTimeout

# Note: vendor SDKs are checked once, here, so a missing extra fails at import with one message
# naming it, not hours into a run.
try:
    from .page import predict, reparse
    from .registry import DEFAULT_TIMEOUT, PROVIDERS, adapter, out_name, resolve, settings_for
except ImportError as exc:
    # Only a missing or incompatible SDK is fixed by installing the extra; a broken import of
    # our own must surface as itself.
    if (exc.name or "").startswith(__name__.split(".")[0]):
        raise
    raise MissingDependency(
        f"the harness could not import what the vendor adapters need:\n"
        f"    {exc}\n"
        f"    pip install 'omni-parse-bench[harness]'"
    ) from None

__all__ = [
    "predict", "reparse", "adapter", "Adapter", "Request", "Call", "Cost",
    "VendorError", "VendorTimeout", "AccountFailure", "MissingCredential", "MissingDependency",
    "PROVIDERS", "DEFAULT_TIMEOUT", "settings_for", "resolve", "out_name",
]
