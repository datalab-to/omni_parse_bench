# GLM-OCR as its SDK self-hosts it, behind one port: vLLM serves the model, the SDK's servers
# (glmocr.server: layout detection, then the model per region) run around it, and server.py hands each
# page to a free one (start.sh). The adapter is providers/glm_ocr.py:
#
#     docker build -t opb-glm-ocr omni_parse_bench/harness/providers/serve/glm-ocr
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-glm-ocr
#     opb init glm-ocr > config.yaml
#     opb run --config config.yaml --set system.glm-ocr.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it; GLM_SDK_CONFIG
# (keep or default) and GLM_SERVERS as server.py says.
FROM vllm/vllm-openai:v0.19.0-ubuntu2404@sha256:69234fc31ff1d5e1687b2f06bba39e0f8c58dd4755f0508dbe0595cd3692b851

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: GLM-OCR's README needs transformers 5.3 or later beside vLLM; pinned at 5.19.0.
RUN /opt/vllm-python -m pip install --no-cache-dir uv \
    && /opt/vllm-python -m uv pip install --python /opt/vllm-python --system --break-system-packages --no-cache \
        transformers==5.19.0
# Note: the SDK runs in a Python of its own, as its README installs it.
RUN /opt/vllm-python -m uv venv /opt/glm --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/glm/bin/python --no-cache 'glmocr[selfhosted,server]==0.1.5' \
        httpx==0.28.1 pyyaml==6.0.3

ENV PORT=8001 GLMOCR_MODE=selfhosted GLMOCR_OCR_API_HOST=127.0.0.1 GLMOCR_OCR_API_PORT=8000 \
    GLMOCR_OCR_MODEL=glm-ocr GLMOCR_LAYOUT_DEVICE=cuda
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
