"""A JSON POST to a model server, within a call's time budget:

- `parse`: one page to an opb model server's /parse route (providers/serve/);
- `post`: any JSON POST, its failures mapped to the harness's errors; and
- `page` and `settings`: what a model server is sent.

A chat endpoint is `providers.llm.chat`.
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
    """An open model adapter's options as its server takes them: every field but `base_url`, `model` (checked
    against the answer) and those the adapter applies itself (`local`)."""
    out = {f.name: getattr(config, f.name) for f in dataclasses.fields(config)}
    return {k: v for k, v in out.items() if k not in ("base_url", "model", *local)}


def parse(config: Any, path: Path, timeout: float, body: dict | None = None) -> dict:
    """An opb model server's answer for one page: `body` (by default the page and `settings`) to /parse at
    `config.base_url`, with OPB_ENDPOINT_KEY as its bearer token when set."""
    body = {**page(path), "settings": settings(config)} if body is None else body
    reply = post(f"{config.base_url.rstrip('/')}/parse", body, budget.Budget(timeout),
                 key=os.environ.get("OPB_ENDPOINT_KEY"))
    # Note: what answered is what the server says it serves, not what the adapter would ask for, so a run
    # records the weights that answered however the server was started. A server that doesn't say is out of
    # date: a bug of the setup, which stops the run, not a failure of the model.
    if not (isinstance(served := reply.get("served"), dict) and "weights" in served):
        raise ValueError(f"the server at {config.base_url} doesn't say what it serves (no \"served\" in its "
                         "reply); rebuild it from its serve folder, whose server.py reports it")
    return reply


def served(base_url: str, deadline: budget.Budget) -> tuple[str, dict]:
    """What a vLLM with no server.py of ours serves: the name it serves under, `<weights>@<revision>` (its
    start.sh's --served-model-name), from its /v1/models, and the same as a server.py's `served`."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/v1/models", timeout=max(1.0, deadline.remaining()))
    except httpx.TransportError as exc:
        if errors.refused(exc): raise
        raise errors.transport(exc, "connection failed") from exc
    with adapter.reading("vLLM's /v1/models"):
        name = r.json()["data"][0]["id"]
    weights, at, revision = name.partition("@")
    if not at:
        raise ValueError(f"the server at {base_url} serves {name!r}, not <weights>@<revision>; rebuild it "
                         "from its serve folder, whose start.sh names it so")
    return name, {"weights": weights, "revision": revision}


def post(url: str, body: dict, deadline: budget.Budget, key: str | None = None) -> dict:
    """The server's JSON answer, within what is left of `deadline`; `key`, if any, as its bearer token."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        # Note: a Modal web endpoint answers a request still running after 150 s with a 303 to a URL that waits for
        # the result (https://modal.com/docs/guide/webhook-timeouts), so a cold start is slow rather than failed.
        r = httpx.post(url, json=body, headers=headers, timeout=max(1.0, deadline.remaining()),
                       follow_redirects=True)
    except httpx.TimeoutException as exc:
        raise errors.SystemTimeout(f"no answer within {deadline.total:g} s") from exc
    except httpx.TransportError as exc:
        if errors.refused(exc): raise
        raise errors.transport(exc, "connection failed") from exc
    if r.status_code != 200:
        raise errors.SystemFailed(f"HTTP {r.status_code}: {r.text}", status=r.status_code, body=r.text)
    with adapter.reading("the server's answer"):
        return contract.json_object(r)
