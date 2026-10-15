"""Which adapter, at what settings, filed under what name.

`ADAPTERS` maps a vendor name to its adapter module; any model id (it contains
`MODEL_SEPARATOR`) routes to the single-shot LLM adapter, with the id as its `model` setting. An
adapter of your own is filed with `add_adapter(name, module)`, or declared by its package under the
entry-point group `ENTRY_POINT_GROUP`, and loaded when first asked for.

The adapter's `Config` is the declaration of its options: what `--options` may set, what
`opb providers` lists, and what a run records. Nothing infers an option from a signature or an
environment variable, so every setting that steered a run appears in it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from importlib import metadata
from types import ModuleType
from typing import Any

from . import contract
from .providers import (azure, chandra_ocr, datalab, deepseek_ocr, dots, extend, glm_ocr, hunyuan, indra_ocr,
                        infinity, lighton, llamaparse, llm, mineru, mistral, nanonets, olmocr, paddleocr_vl,
                        reducto, surya_ocr, tesseract, unlimited)

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
    # Open models, each served from its folder in providers/oss/: the vendor's own code on a server of
    # ours, or vLLM alone where the vendor offers only the model.
    "chandra-ocr": chandra_ocr,
    "deepseek-ocr": deepseek_ocr,
    "dots-mocr": dots,
    "glm-ocr": glm_ocr,
    "hunyuan-ocr": hunyuan,
    "indra-ocr": indra_ocr,
    "infinity-parser2": infinity,
    "lightonocr": lighton,
    "mineru": mineru,
    "nanonets-ocr": nanonets,
    "olmocr": olmocr,
    "paddleocr-vl": paddleocr_vl,
    "surya-ocr": surya_ocr,
    "unlimited-ocr": unlimited,
}
ENTRY_POINT_GROUP = "omni_parse_bench.adapters"
CONTRACT = ("Config", "SUPPORTS", "requests", "call", "parse")   # what an adapter module defines


def plugins() -> dict[str, metadata.EntryPoint]:
    """The adapters installed packages declare under `ENTRY_POINT_GROUP`, by name."""
    out = {}
    # Note: walked per distribution because `metadata.entry_points` keeps one entry per name,
    # silently dropping a second package that claims it.
    for ep in (ep for d in metadata.distributions() for ep in d.entry_points):
        if ep.group != ENTRY_POINT_GROUP: continue
        if (ep.name in ADAPTERS or MODEL_SEPARATOR in ep.name
                or (ep.name in out and out[ep.name].dist.name != ep.dist.name)):
            raise ValueError(f"package {ep.dist.name!r} declares adapter {ep.name!r}, which is taken or "
                             f"contains {MODEL_SEPARATOR!r}. Rename it in its pyproject.toml")
        out[ep.name] = ep
    return out


PLUGINS = plugins()
PROVIDERS = sorted({*ADAPTERS, *PLUGINS})


def add_adapter(provider: str, module: ModuleType, *, replace: bool = False) -> None:
    """File an adapter defined in code; a package declares one under `ENTRY_POINT_GROUP` instead."""
    taken = provider in ADAPTERS or provider in PLUGINS
    if MODEL_SEPARATOR in provider or (taken and not replace):
        raise ValueError(f"adapter name {provider!r} is taken or contains {MODEL_SEPARATOR!r}. Pick another, "
                         "or pass replace=True to replace a taken one")
    if missing := [n for n in CONTRACT if not hasattr(module, n)]:
        raise TypeError(f"adapter {provider!r} is missing {', '.join(missing)}; see harness/contract.py")
    ADAPTERS[provider] = module
    # Note: updated in place because callers hold the list itself (`from .registry import PROVIDERS`).
    PROVIDERS[:] = sorted({*PROVIDERS, provider})


def adapter(provider: str) -> contract.Adapter:
    """The module that talks to this vendor: its `Config`, `SUPPORTS`, `requests` and `call`."""
    if MODEL_SEPARATOR in provider:
        return llm
    if provider not in ADAPTERS and (ep := PLUGINS.get(provider)):
        try:
            add_adapter(provider, ep.load(), replace=True)
        except ImportError as exc:
            exc.add_note(f"while loading adapter {provider!r} from package {ep.dist.name!r}")
            raise
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
    stands for is written beside the answers as `settings.json` by `benchmark.predict_all`. A
    `Config` field marked `metadata={"names_run": False}` is left out: where an opb model server answers
    (a new address each time it starts) doesn't change what was run, so a resumed run keeps its name.
    """
    # Note: what each call sends is in the digest too (fixed request settings, a prompt's digest),
    # so a code change that alters a request names a new run instead of joining the old one.
    api, config = adapter(provider), config_for(provider, options)
    sent = [[sorted(r.outputs), r.sent] for r in api.requests(api.SUPPORTS, config)]
    named = {f.name for f in dataclasses.fields(config) if f.metadata.get("names_run", True)}
    kept = {k: v for k, v in settings_for(provider, options).items() if k in named}
    settings = {"provider": provider, **kept, "requests": sent}
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
