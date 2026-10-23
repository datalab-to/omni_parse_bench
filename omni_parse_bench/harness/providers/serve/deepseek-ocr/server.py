"""DeepSeek-OCR-2's server: steps 1 to 4 of providers/deepseek_ocr.py, on its repository's own vLLM path.

`parse` says what the server answers and how it runs.
"""
import argparse
import asyncio
import base64
import io
import os
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

os.environ["VLLM_USE_V1"] = "0"
VENDOR = "/opt/dsocr2/DeepSeek-OCR2-master/DeepSeek-OCR2-vllm"
sys.path.insert(0, VENDOR)
os.chdir(VENDOR)

from aiohttp import web  # noqa: E402
from config import CROP_MODE, MAX_CONCURRENCY, MODEL_PATH, NUM_WORKERS, PROMPT  # noqa: E402
from deepseek_ocr2 import DeepseekOCR2ForCausalLM  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402
from process.image_process import DeepseekOCR2Processor  # noqa: E402
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor  # noqa: E402
from vllm import AsyncLLMEngine, SamplingParams  # noqa: E402
from vllm.engine.arg_utils import AsyncEngineArgs  # noqa: E402
from vllm.model_executor.models.registry import ModelRegistry  # noqa: E402

ModelRegistry.register_model("DeepseekOCR2ForCausalLM", DeepseekOCR2ForCausalLM)

KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: the vendor's renderer (pdfium, PyMuPDF) isn't thread-safe, and its own tools load one page at a
# time; requests arrive on many threads, so pages load one at a time here too.
LOAD = threading.Lock()
COMMIT = subprocess.run(["git", "-C", "/opt/dsocr2", "rev-parse", "HEAD"], capture_output=True,
                        text=True).stdout.strip() or None
# run_dpsk_ocr2_eval_batch.py: LLM(...) arguments and SamplingParams, verbatim, but for the values the
# request sets (the adapter's options, the script's by default)
ENGINE = AsyncLLMEngine.from_engine_args(AsyncEngineArgs(
    model=MODEL_PATH,
    hf_overrides={"architectures": ["DeepseekOCR2ForCausalLM"]},
    block_size=256,
    enforce_eager=False,
    trust_remote_code=True,
    max_model_len=8192,
    swap_space=0,
    max_num_seqs=MAX_CONCURRENCY,
    tensor_parallel_size=1,
    gpu_memory_utilization=0.7,
))
SAMPLING = ("temperature", "top_p", "max_tokens")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = SAMPLING + ("dpi", "ngram_size", "window_size")


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def sampling(s: dict) -> SamplingParams:
    return SamplingParams(
        **{k: s[k] for k in SAMPLING},
        logits_processors=[NoRepeatNGramLogitsProcessor(ngram_size=s["ngram_size"],
                                                        window_size=s["window_size"],
                                                        whitelist_token_ids={128821, 128822})],
        skip_special_tokens=False,
    )


POOL = ThreadPoolExecutor(NUM_WORKERS)   # the vendor pre-processes images on NUM_WORKERS threads


def load(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """The page as the repository's scripts load one. Copied, not imported: both scripts build the engine
    when imported (Apache-2.0, DeepSeek-OCR2-vllm at 2f3699e). A PDF as run_dpsk_ocr2_pdf.py's
    `pdf_to_images_high_quality` renders it, PyMuPDF at `dpi` through PNG; an image as
    run_dpsk_ocr2_image.py's `load_image` opens it, its EXIF rotation applied."""
    import fitz

    if suffix.lower() != ".pdf":
        return ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
        Image.MAX_IMAGE_PIXELS = None
        return Image.open(io.BytesIO(pix.tobytes("png")))
    finally:
        doc.close()


def page(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """`load`, one page at a time."""
    with LOAD:
        return load(data, suffix, dpi)


def features(data: bytes, suffix: str, dpi: int):
    image = page(data, suffix, dpi).convert("RGB")
    return DeepseekOCR2Processor().tokenize_with_images(images=[image], bos=True, eos=True,
                                                        cropping=CROP_MODE)


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


async def parse(request: web.Request) -> web.Response:
    """The engine, model registration, image processor, logits processor and sampling are the vendor's
    (github.com/deepseek-ai/DeepSeek-OCR-2 at 2f3699e, DeepSeek-OCR2-master/DeepSeek-OCR2-vllm): the engine
    arguments of run_dpsk_ocr2_eval_batch.py on the AsyncLLMEngine of run_dpsk_ocr2_image.py. The repository
    runs it only as batch scripts; the transport is ours. How a page is processed is set out step by step in
    the adapter's docstring.

        GET  /health    200 once the engine is up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"temperature", "top_p", "max_tokens", "dpi", "ngram_size",
                                     "window_size"}}
                        -> {"raw", "tokens", "finish_reason", "prompt",
                            "vendor": {"DeepSeek-OCR-2": its commit}}
    """
    if KEY and request.headers.get("Authorization") != f"Bearer {KEY}":
        return web.json_response({"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"}, status=401)
    body = await request.json()
    s = settings(body)
    feats = await asyncio.get_running_loop().run_in_executor(POOL, features, base64.b64decode(body["page"]),
                                                             body["suffix"], s["dpi"])
    final = None
    async for out in ENGINE.generate({"prompt": PROMPT, "multi_modal_data": {"image": feats}},
                                     sampling(s),
                                     f"req-{uuid.uuid4().hex}"):
        final = out
    o = final.outputs[0]
    return web.json_response({"served": SERVED,
                              "raw": o.text, "tokens": len(o.token_ids), "finish_reason": o.finish_reason,
                              "prompt": PROMPT, "vendor": {"DeepSeek-OCR-2": COMMIT}})


async def served(request: web.Request) -> web.Response:
    return web.json_response(SERVED)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "model": MODEL_PATH})


app = web.Application(client_max_size=64 * 1024 * 1024)
app.add_routes([web.get("/health", health), web.get("/served", served), web.post("/parse", parse)])

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    web.run_app(app, host="0.0.0.0", port=ap.parse_args().port)
