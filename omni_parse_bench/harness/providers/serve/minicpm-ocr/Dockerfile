# The release requires upstream's pinned vLLM/Transformers source build. The SDK and Paddle run in
# a separate environment, as the vendor documents. No speculative draft model or test-time selector.
FROM nvidia/cuda:13.0.2-devel-ubuntu22.04@sha256:1c517d4fb96528c8999e14e6e6b16d7e2ff9ae8d194fd788d60fdc88e693e982

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git software-properties-common libdw-dev libelf-dev libgomp1 libglib2.0-0 libgl1 \
    && add-apt-repository -y ppa:ubuntu-toolchain-r/test && apt-get update \
    && apt-get install -y --no-install-recommends gcc-13 g++-13 \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/0.13.5/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Fetch only the SDK and installer text/source; the model repository's example images are not needed.
RUN git init /opt/minicpm && cd /opt/minicpm \
    && git remote add origin https://github.com/OpenBMB/MiniCPM-OCR.git \
    && git sparse-checkout set --no-cone /pyproject.toml /scripts/install.sh /scripts/prepare_cuda_nvcc.py /sdk/ \
    && git fetch --filter=blob:none --depth=1 origin d9de88090765c2895c5ca192699da099f79e3fed \
    && git checkout --detach FETCH_HEAD
# The installer needs a libcuda link during compilation; a build has CUDA's stub, no loaded driver.
RUN OCR_LIBCUDA=/usr/local/cuda/lib64/stubs/libcuda.so bash /opt/minicpm/scripts/install.sh vllm
# PaddleX constructs a PDFReader while loading the layout predictor, including for image inputs.
RUN uv venv /opt/sdk --python 3.12 \
    && uv pip install --python /opt/sdk/bin/python '/opt/minicpm/sdk[layout,pdf]' \
        paddlepaddle==3.2.1 paddlex==3.4.2 pypdfium2==5.14.0 fastapi==0.143.0 uvicorn==0.54.0

ENV PORT=8001 CC=gcc-13 CXX=g++-13 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
COPY server.py worker.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
