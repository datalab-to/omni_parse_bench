# PaddleOCR-VL-1.6 as its vendor runs it, behind one port: vLLM serves the VLM, server.py runs
# PaddleOCR's own page pipeline (layout model, then the VLM per block) around it (start.sh). The
# adapter is providers/paddleocr_vl.py:
#
#     docker build -t opb-paddleocr_vl omni_parse_bench/harness/providers/oss/paddleocr_vl
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-paddleocr_vl
#     opb benchmark --providers paddleocr-vl --options '{"paddleocr-vl": {"base_url": "http://localhost:8001"}}'
#
# The weights download when it starts, into HF_HOME (the layout model too); mount a cache there to keep
# them. Set OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.31.0

RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 && rm -rf /var/lib/apt/lists/*
# Note: the pipeline runs in a Python of its own: paddlepaddle's packages don't share vLLM's.
RUN python3 -m pip install --no-cache-dir uv && uv venv /opt/paddle --python 3.12 \
    && uv pip install --python /opt/paddle/bin/python --no-cache paddlepaddle==3.3.1 \
        'paddleocr[doc-parser]==3.7.0' fastapi uvicorn httpx
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python

ENV PORT=8001 PADDLE_PDX_MODEL_SOURCE=huggingface PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    VLLM_USE_FLASHINFER_SAMPLER=0
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
