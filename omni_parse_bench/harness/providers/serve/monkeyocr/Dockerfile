# MonkeyOCR-pro-3B as its repository documents running it, behind one port: its own `MonkeyOCR` class
# (PP-DocLayoutV2 layout, layoutreader reading order, then the 3B model per block through LMDeploy, the
# backend its install guide recommends and its model_configs.yaml sets), run by server.py (start.sh). The
# adapter is providers/monkeyocr.py:
#
#     docker build -t opb-monkeyocr omni_parse_bench/harness/providers/serve/monkeyocr
#     docker run --gpus all -p 8001:8001 -v ~/.cache/monkeyocr:/app/MonkeyOCR/model_weight opb-monkeyocr
#     opb init monkeyocr > config.yaml
#     opb run --config config.yaml --set system.monkeyocr.base_url=http://localhost:8001
#
# The weights (recognition model, layout model and reading-order model, one Hugging Face repository)
# download when it starts, into model_weight; mount a directory there to keep them. Set OPB_ENDPOINT_KEY
# (docker run -e) to require it as a bearer token, as opb sends it.
#
# Licenses: the code is Apache-2.0; the MonkeyOCR v1 weights are for academic research and non-commercial
# evaluation only (README, "License and Commercial Use"). The image holds the code, never the weights.
#
# Note: the environment is the repository's Dockerfile (docker/Dockerfile) and install guide
# (docs/install_cuda_pp.md) as written: CUDA 12.6, torch 2.6.0, paddlepaddle-gpu 3.0.0, paddlex 3.3.0,
# lmdeploy 0.9.2.
#
# GPUs (expected, nothing launched): x86-64 with an H100 (Hopper, compute capability 9.0) should work: CUDA
# 12.6 and torch 2.6.0 support it, and the README reports H800, A100, H200 and L20 runs. This image is not
# meant for a B200 (Blackwell, 10.0, needs CUDA 12.8 and torch 2.7 or later; the repository documents no run
# on one, so expect a failure, not a slow run). GH200 is aarch64: the pinned paddlepaddle-gpu 3.0.0 wheel
# from Paddle's index, and the base image, would need aarch64 builds; not expected to work as written.
# For a 20/30/40-series card or V100 the README asks for the patched LMDeploy (`tools/lmdeploy_patcher.py`);
# not needed on H100.
FROM nvidia/cuda:12.6.3-runtime-ubuntu22.04@sha256:63a18dd805367dacfb077aeced8384ab2fb569598ec5f5f5220c3f90a5c23650

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-dev python3-pip libgl1-mesa-glx libglib2.0-0 git curl wget poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python && ln -sf /usr/bin/pip3 /usr/bin/pip
ENV PIP_NO_CACHE_DIR=1
ARG CUDA_VERSION=126
ARG MONKEYOCR_COMMIT=73dee40fef504ed73ba70f5a43038f692bd4b329

RUN git clone https://github.com/Yuliang-Liu/MonkeyOCR.git /app/MonkeyOCR \
    && git -C /app/MonkeyOCR checkout "$MONKEYOCR_COMMIT"
WORKDIR /app/MonkeyOCR

RUN pip install --upgrade pip setuptools huggingface_hub==0.34.4
# Note: PP-DocLayoutV2 needs PaddlePaddle and PaddleX (docs/install_cuda_pp.md, step 1).
RUN pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu${CUDA_VERSION}/ \
    && pip install "paddlex[base]==3.3.0" langchain==0.3.26
RUN pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
        --index-url https://download.pytorch.org/whl/cu${CUDA_VERSION}
RUN pip install -e . && pip install lmdeploy==0.9.2

ENV PORT=8001 MODEL_REPO=echo840/MonkeyOCR-pro-3B
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
