# Unlimited-OCR 2 as its model card serves it, behind one port: the vendor's SGLang build serves the model,
# server.py loads the page and asks it as the model card's client does (start.sh).
# The adapter is providers/unlimited_ocr2.py:
#
#     docker build -t opb-unlimited-ocr-2 omni_parse_bench/harness/providers/serve/unlimited-ocr-2
#     docker run --gpus all --shm-size 16g -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-unlimited-ocr-2
#     opb init unlimited-ocr-2 > config.yaml
#     opb run --config config.yaml --set system.unlimited-ocr-2.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM nvidia/cuda:13.0.1-devel-ubuntu22.04@sha256:93a8d207db5aaa6384f834a6bf70d417433f709e61b57a91e7cc99c16172f49c

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates libnuma1 python3 \
    && rm -rf /var/lib/apt/lists/*
# Note: the model card's setup: Python 3.10, the customized SGLang wheel shipped in the weights' repository
# (at the revision start.sh serves), and PyMuPDF.
RUN curl -LsSf https://astral.sh/uv/0.9.5/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv venv /venv --python 3.10 \
    && curl -LsSf -o /tmp/sglang-0.5.20.dev10+g8d62f5fb9c-py3-none-any.whl https://huggingface.co/baidu/Unlimited-OCR-2/resolve/5632329a32e103d5f1add270681e0f5c1233c6e4/wheel/sglang-0.5.20.dev10+g8d62f5fb9c-py3-none-any.whl \
    && uv pip install --python /venv/bin/python --no-cache /tmp/sglang-0.5.20.dev10+g8d62f5fb9c-py3-none-any.whl \
        pymupdf==1.27.2.2 httpx==0.28.1 \
    && rm /tmp/*.whl

ENV PORT=8001 PYTHONPATH=/srv
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
