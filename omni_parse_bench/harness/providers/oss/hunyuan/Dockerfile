# HunyuanOCR-1.5 as its own client runs it, behind one port: vLLM serves the model, server.py asks it
# as the repository's client does, with its streaming early stop and its post-processing (start.sh).
# The adapter is providers/hunyuan.py:
#
#     docker build -t opb-hunyuan omni_parse_bench/harness/providers/oss/hunyuan
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-hunyuan
#     opb benchmark --providers hunyuan-ocr --options '{"hunyuan-ocr": {"base_url": "http://localhost:8001"}}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it. The repository's
# code is cloned into the image and runs there; its license is the repository's.
FROM nvidia/cuda:12.8.1-devel-ubuntu24.04@sha256:520292dbb4f755fd360766059e62956e9379485d9e073bbd2f6e3c20c270ed66

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Note: the vendor's validated setup: vLLM 0.18.1 on Python 3.10.
RUN curl -LsSf https://astral.sh/uv/0.9.5/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv venv /venv --python 3.10 \
    && uv pip install --python /venv/bin/python --no-cache 'vllm==0.18.1' 'openai==2.24.0' 'pillow==12.3.0' \
        huggingface_hub==0.36.2
RUN git clone -q https://github.com/Tencent-Hunyuan/HunyuanOCR /opt/hunyuan && git -C /opt/hunyuan checkout -q 1ef4179e53cf860f7e6fd8276a292e5d05b3e927

ENV PORT=8001 PYTHONPATH=/opt/hunyuan HF_HUB_ENABLE_HF_TRANSFER=0
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
