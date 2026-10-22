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
import difflib
import hashlib
import json
import re
import typing
from importlib import metadata
from types import ModuleType
from typing import Any

from omni_parse_bench import errors as base_errors

from . import contract
from .providers import (azure, chandra_ocr, datalab, deepseek_ocr, dots, extend, glm_ocr, hunyuan, indra_ocr,
                        infinity, lighton, llamaparse, llm, mineru, mistral, nanonets, nemotron_parse, olmocr,
                        paddleocr_vl, reducto, surya_ocr, tesseract, unlimited)

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
    # Open models, each served from its folder in providers/serve/: the vendor's own code on a server of
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
    "nemotron-parse": nemotron_parse,
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
        raise base_errors.UsageError(f"unknown provider {provider!r}. Known vendors: "
                                     f"{', '.join(PROVIDERS)}. Any OpenRouter model id also works, "
                                     f"e.g. openai/gpt-5.6-sol")
    return ADAPTERS[provider]


def resolve(provider: str) -> str:
    """The name of the adapter `provider` reaches, which groups its runs into one pool: what `WORKERS` and
    `--workers` are keyed by. One of ours is its module's short name (`llm` for every model id); one of
    yours is the name it was filed or declared under (`add_adapter`, `ENTRY_POINT_GROUP`).

    Note: not an outside module's name: that is an internal path its user never typed, and two packages'
    modules may end in the same word."""
    return _name(provider, adapter(provider))


def adapter_names() -> frozenset[str]:
    """`resolve`'s name for every adapter filed so far, and `llm`, every model id's."""
    return frozenset(_name(p, m) for p, m in ADAPTERS.items()) | {"llm"}


def _name(provider: str, module: ModuleType) -> str:
    """`resolve`'s name for the adapter `module`, filed under `provider`."""
    name = module.__name__
    return name.rsplit(".", 1)[-1] if name.startswith(f"{__package__}.providers.") else provider


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
            raise base_errors.UsageError(
                f"{provider}: `model` is the provider name, not an option -- otherwise the "
                f"run would be stored and published under a model it did not use. Run the "
                f"one you want: --providers {options['model']}")
        options = {**options, "model": provider}
    try:
        hints = typing.get_type_hints(config_type)
    except (NameError, TypeError):   # Note: an annotation that doesn't resolve leaves its value unchecked.
        hints = {}
    fields = [f.name for f in dataclasses.fields(config_type)]
    if unknown := sorted(set(options) - set(fields)):
        near = difflib.get_close_matches(unknown[0], fields, n=1)
        raise base_errors.UsageError(f"{provider} has no option {unknown[0]!r}"
                                     + (f" (did you mean {near[0]!r}?)" if near else "")
                                     + f"; its options are: {', '.join(fields) or '(none)'}")
    for name, value in options.items():
        if (want := hints.get(name)) in (str, int, float, bool) and not _of(value, want):
            raise base_errors.UsageError(f"{provider}: option {name} is a {want.__name__}, not {value!r}")
        # Note: NaN and infinity are no JSON, and a run's settings are written as JSON.
        if not _finite(value):
            raise base_errors.UsageError(f"{provider}: option {name} is {value!r}; give a finite number")
    # Note: a whole number given for a float option becomes that float, so 0 and the default 0.0 are one
    # setting and name one run, not two.
    options = {k: float(v) if hints.get(k) is float else v for k, v in options.items()}
    try:
        return config_type(**options)
    except ValueError as exc:   # Note: an adapter's own check of a value (`__post_init__`).
        if isinstance(exc, base_errors.UsageError): raise
        raise base_errors.UsageError(f"{provider}: {exc}") from None


def _finite(value: Any) -> bool:
    """Whether `value` is JSON without NaN or infinity anywhere in it."""
    try:
        json.dumps(value, allow_nan=False, default=str)
    except ValueError:
        return False
    return True


def _of(value: Any, want: type) -> bool:
    """Whether `value` is a `want` as JSON gives one: an int is a float, and a bool is no number."""
    if want is float: return isinstance(value, int | float) and not isinstance(value, bool)
    if want is int: return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, want)


def settings_for(provider: str, options: dict | None = None) -> dict:
    """The `Config` the adapter will be handed, as a plain dict. Holds no credentials."""
    return dataclasses.asdict(config_for(provider, options))
