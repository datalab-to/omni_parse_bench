# Unlimited-OCR 2 as Unlimited-OCR's vLLM recipe runs it, on the vLLM build the recipe names, behind one port:
# vLLM serves the model, server.py loads the page as its repository's pipeline does and asks it (start.sh).
# The adapter is providers/unlimited_ocr2.py:
#
#     docker build -t opb-unlimited-ocr-2 omni_parse_bench/harness/providers/serve/unlimited-ocr-2
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-unlimited-ocr-2
#     opb init unlimited-ocr-2 > config.yaml
#     opb run --config config.yaml --set system.unlimited-ocr-2.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:unlimited-ocr-cu129@sha256:e45cf562cbc885af2531f576e79377069e0a6f0af42cdad7658b8494185a1143

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
RUN /opt/vllm-python -m pip install --no-cache-dir uv \
    && /opt/vllm-python -m uv pip install --python /opt/vllm-python --system --break-system-packages --no-cache \
        httpx==0.28.1 requests==2.34.2 pymupdf==1.28.2
RUN git clone -q https://github.com/baidu/Unlimited-OCR /opt/unlimited \
    && git -C /opt/unlimited checkout -q 92ad94b53a51950fea0416aced42331dfb4dd59e

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
