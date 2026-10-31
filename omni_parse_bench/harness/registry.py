"""Which adapter a provider name means:

- `ADAPTERS`: each name's class. A model id (it contains `MODEL_SEPARATOR`, as `openai/gpt-5.6-sol`) means
  the single-shot LLM adapter, with the id as its `model`;
- `PLUGINS`: adapters other packages declare under the entry-point group `ENTRY_POINT_GROUP`, loaded the
  first time they are asked for; and
- `system`: an adapter made from a config's options.
"""
from __future__ import annotations

from importlib import metadata
from typing import Any

from omni_bench_core import adapter as core



# Note: we check the systems' packages once, here, so a missing extra fails at import with one message naming
# it, not hours into a run.
try:
    from .adapter import Parser
    from .providers import (
        azure,
        chandra_ocr,
        datalab,
        deepseek_ocr,
        dots,
        extend,
        glm_ocr,
        hunyuan,
        indra_ocr,
        infinity,
        lighton,
        llamaparse,
        llm,
        mineru,
        minicpm_ocr,
        mistral,
        nanonets,
        nemotron_parse,
        olmocr,
        ovisocr,
        ovisocr2,
        ovisocr3,
        oxr,
        paddleocr_vl,
        reducto,
        surya_ocr,
        surya_ocr25,
        tesseract,
        unlimited,
        unlimited_ocr2,
    )
except ImportError as exc:
    # Note: only a missing or incompatible package is fixed by installing the extra; a broken import of our
    # own must surface as itself.
    if (exc.name or "").startswith(__name__.split(".")[0]):
        raise
    exc.add_note("the harness could not import what the adapters need: "
                 "pip install 'omni-parse-bench[harness]'")
    raise

MODEL_SEPARATOR = "/"
ENTRY_POINT_GROUP = "omni_parse_bench.adapters"

ADAPTERS: dict[str, type[Parser]] = {a.name: a for a in (
    datalab.Datalab, reducto.Reducto, extend.Extend, llamaparse.LlamaParse, azure.Azure, mistral.Mistral,
    tesseract.Tesseract,
    # Open models, each served from its folder in providers/serve/: the vendor's own code on a server of ours,
    # or vLLM alone where the vendor offers only the model.
    chandra_ocr.ChandraOcr, deepseek_ocr.DeepseekOcr, dots.Dots, glm_ocr.GlmOcr, hunyuan.Hunyuan,
    indra_ocr.IndraOcr, infinity.Infinity, lighton.LightOn, mineru.MinerU, nanonets.Nanonets,
    nemotron_parse.NemotronParse, olmocr.OlmOcr, minicpm_ocr.MiniCpmOcr, oxr.Oxr,
    ovisocr.OvisOcr, ovisocr2.OvisOcr2, ovisocr3.OvisOcr3,
    paddleocr_vl.PaddleOcrVl, surya_ocr.SuryaOcr, surya_ocr25.SuryaOcr25, unlimited.UnlimitedOcr,
    unlimited_ocr2.UnlimitedOcr2)}


def plugins() -> dict[str, metadata.EntryPoint]:
    """The adapters installed packages declare under `ENTRY_POINT_GROUP`, by name."""
    out = {}
    # Note: we walk each distribution because `metadata.entry_points` keeps one entry per name, and would
    # silently drop a second package that claims the same name.
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


def adapter_class(provider: str) -> type[Parser]:
    """The class a provider name means."""
    if MODEL_SEPARATOR in provider: return llm.LLM
    if provider not in ADAPTERS and (ep := PLUGINS.get(provider)):
        try:
            ADAPTERS[provider] = ep.load()
        except ImportError as exc:
            exc.add_note(f"while loading adapter {provider!r} from package {ep.dist.name!r}")
            raise
    if provider not in ADAPTERS:
        raise ValueError(f"unknown system {provider!r}. Known: {', '.join(PROVIDERS)}. Any "
                         "OpenRouter model id also works, e.g. openai/gpt-5.6-sol")
    return ADAPTERS[provider]


def system(provider: str, options: dict[str, Any] | None = None) -> Parser:
    """The adapter `provider` names, at `options`, checked (`omni_bench_core.adapter.configure`). A model id
    is the LLM adapter with that `model`; a `model` option other than it is refused."""
    options = dict(options or {})
    if MODEL_SEPARATOR in provider:
        if options.get("model", provider) != provider:
            raise ValueError(f"{provider}: its `model` is its name, not {options['model']!r}, so a run is "
                             f"never filed under a model it did not use; to run {options['model']}, write "
                             f"its config: opb init {options['model']}")
        options["model"] = provider
    try:
        return core.configure(adapter_class(provider), options)
    except ValueError as exc:   # Note: the core's check of an option, or the adapter's own (`__post_init__`).
        exc.add_note(f"in the options of {provider}")
        raise
