# LightOnOCR-3 (4B or 0.8B) as its own client runs it, behind one port: vLLM serves the model, server.py
# asks it as the `lightonocr` client does and applies the client's repair of the reply (start.sh). The
# adapter is providers/lighton.py:
#
#     docker build -t opb-lighton omni_parse_bench/harness/providers/oss/lighton
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-lighton
#     opb benchmark --providers lightonocr --options '{"lightonocr": {"base_url": "http://localhost:8001"}}'
#
# MODEL picks the model (docker run -e MODEL=lightonai/LightOnOCR-3-0.8B; the 4B by default), and opb's
# `model` option names the same one. The weights download when it starts, into HF_HOME; mount a cache
# there to keep them. Set OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb
# sends it.
FROM vllm/vllm-openai:v0.30.0@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90

RUN apt-get update && apt-get install -y --no-install-recommends git curl poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: the client runs in a Python of its own, as a user installs it beside a vLLM server.
RUN /opt/vllm-python -m pip install --no-cache-dir uv && /opt/vllm-python -m uv venv /opt/lighton --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/lighton/bin/python --no-cache httpx==0.28.1 pdf2image==1.17.0 pypdf==6.20.1 \
        'lightonocr @ git+https://github.com/lightonai/LightOnOCR@36755d461be079737860a5f03ae0c803501269e9'

ENV PORT=8001 MODEL=lightonai/LightOnOCR-3-4B
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
