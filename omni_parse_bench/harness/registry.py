"""Which adapter, at what settings, filed under what name.

`ADAPTERS` maps a vendor name to its adapter module; any model id (it contains
`MODEL_SEPARATOR`) routes to the single-shot LLM adapter, with the id as its `model` setting.

The adapter's `Config` is the declaration of its options: what `--options` may set, what
`opb providers` lists, and what a run records. Nothing infers an option from a signature or an
environment variable, so every setting that steered a run appears in it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any

from . import contract
from .providers import azure, datalab, extend, llamaparse, llm, mistral, reducto, tesseract

DEFAULT_TIMEOUT = 900.0
MODEL_SEPARATOR = "/"

ADAPTERS = {
    "datalab": datalab,
    "reducto": reducto,
    "extend": extend,
    "llamaparse": llamaparse,
    "azure": azure,
    "mistral": mistral,
    "tesseract": tesseract,
}
PROVIDERS = sorted(ADAPTERS)


def adapter(provider: str) -> contract.Adapter:
    """The module that talks to this vendor: its `Config`, `SUPPORTS`, `requests` and `call`."""
    if MODEL_SEPARATOR in provider:
        return llm
    if provider not in ADAPTERS:
        raise ValueError(f"unknown provider {provider!r}. Known vendors: "
                         f"{', '.join(PROVIDERS)}. Any OpenRouter model id also works, "
                         f"e.g. openai/gpt-5.6-sol")
    return ADAPTERS[provider]


def resolve(provider: str) -> str:
    """This adapter's module name; groups every model id that reaches the same adapter."""
    return adapter(provider).__name__.rsplit(".", 1)[-1]


def out_name(provider: str, options: dict | None = None) -> str:
    """A run's directory name: the sanitised provider, and a digest of all its settings.

    Note: the digest covers every setting, not only those that differ from the defaults, so a
    directory holds exactly one configuration even after a default changes. What the digest
    stands for is written beside the answers as `settings.json` by `benchmark.predict_all`.
    """
    # Note: what each call sends is in the digest too (fixed request settings, a prompt's digest),
    # so a code change that alters a request names a new run instead of joining the old one.
    api, config = adapter(provider), config_for(provider, options)
    sent = [[sorted(r.outputs), r.sent] for r in api.requests(api.SUPPORTS, config)]
    settings = {"provider": provider, **settings_for(provider, options), "requests": sent}
    spelled = json.dumps(settings, sort_keys=True, default=str)
    digest = hashlib.sha256(spelled.encode()).hexdigest()[:8]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", provider.replace(MODEL_SEPARATOR, "__"))
    return f"{name}-{digest}"


def config_for(provider: str, options: dict | None = None) -> Any:
    """This provider's adapter `Config`, with the caller's options applied.

    An option the `Config` does not have is refused by name rather than ignored, since an
    ignored typo would run as stock.
    """
    config_type = adapter(provider).Config
    options = options or {}
    if MODEL_SEPARATOR in provider:
        if "model" in options:
            raise ValueError(
                f"{provider}: `model` is the provider name, not an option -- otherwise the "
                f"run would be stored and published under a model it did not use. Run the "
                f"one you want: --providers {options['model']}")
        options = {**options, "model": provider}
    try:
        return config_type(**options)
    except TypeError as exc:
        known = ", ".join(f.name for f in dataclasses.fields(config_type)) or "(none)"
        raise ValueError(f"{provider}: {exc}. Its options are: {known}") from None


def settings_for(provider: str, options: dict | None = None) -> dict:
    """The `Config` the adapter will be handed, as a plain dict. Holds no credentials."""
    return dataclasses.asdict(config_for(provider, options))
