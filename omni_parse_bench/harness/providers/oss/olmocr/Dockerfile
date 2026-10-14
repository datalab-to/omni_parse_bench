# olmOCR 2 as its pipeline runs it, behind one port: vLLM serves the model, server.py runs each page
# through the pipeline's own process_page (start.sh). The adapter is providers/olmocr.py:
#
#     docker build -t opb-olmocr omni_parse_bench/harness/providers/oss/olmocr
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-olmocr
#     opb benchmark --providers olmocr --options '{"olmocr": {"base_url": "http://localhost:8001"}}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.11.2@sha256:2c908d5a84ed251b6a17d179f42d06df1aff353007779ac5eecd8a0ea3fe9331

# Note: poppler-utils for the pipeline's own render (pdftoppm) and the fonts it renders documents with, as
# its own Dockerfile installs them (github.com/allenai/olmocr at f7cfe4c, Dockerfile; Apache-2.0), with its
# switch of the python3 alternative so APT's scripts run on the distribution's Python.
RUN DIST_PY=$(ls /usr/bin/python3.[0-9]* | sort -V | head -n1) && \
    if update-alternatives --query python3 >/dev/null 2>&1; then \
        ORIGINAL_PY=$(update-alternatives --query python3 | awk -F": " '/Value:/ {print $2}'); \
    else \
        ORIGINAL_PY=/usr/bin/python3.12; \
    fi && \
    update-alternatives --install /usr/bin/python3 python3 ${DIST_PY} 1 && \
    update-alternatives --set python3 ${DIST_PY} && \
    apt-get update -y && \
    echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3-apt update-notifier-common poppler-utils fonts-crosextra-caladea fonts-crosextra-carlito \
        gsfonts lcdf-typetools ttf-mscorefonts-installer git curl && \
    update-alternatives --install /usr/bin/python3 python3 ${ORIGINAL_PY} 1 && \
    update-alternatives --set python3 ${ORIGINAL_PY} && \
    rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: the pipeline's package runs in a Python of its own, without its GPU extras; img2pdf is the command
# it calls to make an image file a PDF, which its package doesn't install.
RUN /opt/vllm-python -m pip install --no-cache-dir uv && /opt/vllm-python -m uv venv /opt/olmocr --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/olmocr/bin/python --no-cache aiohttp img2pdf==0.6.3 \
        'olmocr @ git+https://github.com/allenai/olmocr@f7cfe4c22098b154c76b6ec950d1c0a464eecf8d'

ENV PORT=8001 OLMOCR_COMMIT=f7cfe4c22098b154c76b6ec950d1c0a464eecf8d
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
