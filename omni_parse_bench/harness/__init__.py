"""Producing predictions: opb's adapters, one per parsing system (`pip install 'omni-parse-bench[harness]'`).

    adapter.py       `PageAdapter`, the base class of every adapter; its docstring says how to write one
    contract.py      `Request`, `Call` and `Cost`: one call to a system and its answer
    errors.py        how a call fails, and whether a retry can fix it
    budget.py        one page's share of the clock
    layout.py        a system's layout blocks as the `blocks` output
    raster.py        a PDF page as an image, for systems that take images
    http.py          a JSON POST to a model server
    registry.py      which adapter a provider name means, made from a config's options
    providers/       one module per system
"""
# Note: the registry first: it checks, once, that the adapters' packages are installed.
from .registry import ADAPTERS, PROVIDERS, adapter_class, system  # isort: skip
from .adapter import Input, PageAdapter
from .contract import Call, Cost, Request

__all__ = ["ADAPTERS", "Call", "Cost", "Input", "PROVIDERS", "PageAdapter", "Request",
           "adapter_class", "system"]
