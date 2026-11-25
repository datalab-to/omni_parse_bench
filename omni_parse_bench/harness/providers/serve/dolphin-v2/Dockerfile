# Dolphin-v2 as its repository documents running it (`demo_page.py`, Hugging Face transformers), behind one
# port: server.py runs the repository's own two-stage page parse (layout and reading order in one call, then
# the elements, batched by type). The adapter is providers/dolphin_v2.py:
#
#     docker build -t opb-dolphin-v2 omni_parse_bench/harness/providers/serve/dolphin-v2
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-dolphin-v2
#     opb init dolphin-v2 > config.yaml
#     opb run --config config.yaml --set system.dolphin-v2.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set OPB_ENDPOINT_KEY
# (docker run -e) to require it as a bearer token, as opb sends it.
#
# Licenses: the repository's and the weights' LICENSE files are both the Qwen RESEARCH LICENSE AGREEMENT
# (non-commercial: "for research or evaluation purposes only"); the README's badge and the code files'
# headers say MIT, which the LICENSE file contradicts. Treat both code and weights as non-commercial.
#
# Note: the environment is the repository's requirements.txt (torch 2.6.0, transformers 4.51.0, ...) as
# written; its unpinned packages are pinned here to the newest release before Dolphin-v2's (2025-12-12).
#
# GPUs (expected, nothing launched): x86-64 with an H100 (Hopper, compute capability 9.0) should work: the
# pytorch/pytorch 2.6.0 CUDA 12.4 image supports it. A B200 (Blackwell, 10.0) needs torch 2.7 or later with CUDA
# 12.8; this image's torch 2.6.0 does not have that, and the repository documents no run on one, so expect a
# failure there. GH200 is aarch64: this x86-64 image would need an aarch64 PyTorch base and wheels
# (opencv, deepspeed, ...); not expected to work as written.
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime@sha256:77f17f843507062875ce8be2a6f76aa6aa3df7f9ef1e31d9d7432f4b0f563dee

RUN apt-get update && apt-get install -y --no-install-recommends git curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
ENV PIP_NO_CACHE_DIR=1
ARG DOLPHIN_COMMIT=befa5dad986f86396b73cbd8c37e557b5770c902

RUN git clone https://github.com/bytedance/Dolphin.git /app/Dolphin \
    && git -C /app/Dolphin checkout "$DOLPHIN_COMMIT"
WORKDIR /app/Dolphin
RUN pip install -r requirements.txt qwen-vl-utils==0.0.14 matplotlib==3.10.8 jieba==0.42.1 \
        opencv-python==4.12.0.88 bs4==0.0.2 huggingface_hub

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
