"""A JSON POST within a call's time budget, its failures mapped to the harness's errors.

For a server that answers one route with JSON: a vendor's pipeline or its own engine behind one
endpoint, as every opb model server (providers/serve/) answers `/parse` (`parse`). A chat endpoint is
`providers.llm.chat`.
"""
from __future__ import annotations

import base64
import dataclasses
import os
from pathlib import Path
from typing import Any

import httpx
from omni_bench_core import adapter

from . import budget, contract, errors

ENDPOINT_KEY = "OPB_ENDPOINT_KEY, if set, is sent to the model server as its bearer token"


def page(path: Path) -> dict:
    """The page file as an opb model server takes it (providers/serve/): its bytes and its suffix, for the
    vendor's own code to load as it loads a PDF or an image."""
    return {"page": base64.b64encode(path.read_bytes()).decode("ascii"), "suffix": path.suffix.lower()}


def settings(config: Any, *local: str) -> dict:
    """An open model adapter's options as its server takes them: every field but where the server is
    (`base_url`), the model it serves (`model`, checked against its answer) and those the adapter applies
    itself (`local`). Each defaults to the vendor's value; any other value is another configuration, and
    gets its own run folder."""
    out = {f.name: getattr(config, f.name) for f in dataclasses.fields(config)}
    return {k: v for k, v in out.items() if k not in ("base_url", "model", *local)}


def parse(config: Any, path: Path, timeout: float, body: dict | None = None) -> dict:
    """An opb model server's answer for one page: `body` (by default the page file and the config's
    `settings`) to its /parse route at `config.base_url`, within `timeout`, with OPB_ENDPOINT_KEY as its
    bearer token when it is set."""
    body = {**page(path), "settings": settings(config)} if body is None else body
    return post(f"{config.base_url.rstrip('/')}/parse", body, budget.Budget(timeout),
                key=os.environ.get("OPB_ENDPOINT_KEY"))


def post(url: str, body: dict, deadline: budget.Budget, key: str | None = None) -> dict:
    """The server's JSON answer, within what is left of `deadline`; `key`, if any, as its bearer token."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        r = httpx.post(url, json=body, headers=headers, timeout=max(1.0, deadline.remaining()))
    except httpx.TimeoutException as exc:
        raise errors.SystemTimeout(f"no answer within {deadline.total:g} s") from exc
    except httpx.TransportError as exc:
        if errors.refused(exc): raise errors.NoServer(url) from exc
        raise errors.transport(exc, "connection failed") from exc
    if r.status_code != 200:
        raise errors.SystemFailed(f"HTTP {r.status_code}: {r.text}", status=r.status_code, body=r.text)
    with adapter.reading("the server's answer"):
        return contract.json_object(r)
