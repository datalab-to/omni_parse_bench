#!/usr/bin/env bash
# server.py answers on $PORT with one converter per uvicorn worker, each reading one page at a time and loading
# its own models on the device Docling picks (the GPU when torch finds one, else the CPU). No vLLM.
#
# WORKERS (docker run -e) sets how many. Its default is 4 on a B200: each loaded worker uses about 3 GB and can
# reach about 7 GB under load (about 22 GB total at peak on the B200); budget about 24 GB for four workers. Set
# fewer workers on smaller GPUs. On the CPU the default is 2, as each worker's models already use several threads
# (Docling's num_threads, 4 by default).
set -euo pipefail
if [[ -z "${WORKERS:-}" ]]; then
    # Note: the same test Docling's `auto` device makes (docling/utils/accelerator_utils.py, decide_device).
    if [[ "${DOCLING_DEVICE:-auto}" != cpu ]] && python -c "import sys, torch; sys.exit(not torch.cuda.is_available())"; then
        WORKERS=4
    else
        WORKERS=2
    fi
fi
exec uvicorn server:app --app-dir /srv --host 0.0.0.0 --port "${PORT:-8001}" --workers "$WORKERS"
