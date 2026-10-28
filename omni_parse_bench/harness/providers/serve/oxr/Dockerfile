# OXR-1.0 as SoMark's all-in-one image runs it (docker/Dockerfile.allinone at the pinned commit): the D-FINE layout
# service, vLLM with the model's plugin and the OXR parsing API, each on loopback; server.py answers opb on 8001
# (start.sh). The adapter is providers/oxr.py:
#
#     docker build -t opb-oxr omni_parse_bench/harness/providers/serve/oxr
#     docker run --gpus all --ipc=host -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-oxr
#     opb init oxr > config.yaml
#     opb run --config config.yaml --set system.oxr.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set OPB_ENDPOINT_KEY
# (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.25.1@sha256:e4f88a835143cd22aee2397a26ec6bb80b3a4a6fe0c882bcbc63822904766089

RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*
# Note: git -C, not cd: a sky run builds these steps in one shell, where a cd would outlast the step.
RUN git init /app && git -C /app remote add origin https://github.com/SoMarkAI/OXR.git \
    && git -C /app fetch --depth=1 origin c1a1dcb312ee9f691404f127785510453c0d9350 \
    && git -C /app checkout --detach FETCH_HEAD
# Note: the vendor's three environments, as its Dockerfile makes them; only vLLM's sees the base image's runtime pins.
RUN python3 -m venv --system-site-packages /opt/vllm-venv \
    && /opt/vllm-venv/bin/python -m pip install --no-cache-dir 'setuptools>=69' wheel \
    && python3 -m venv --system-site-packages /opt/oxr-venv \
    && /opt/oxr-venv/bin/python -m pip install --no-cache-dir -c /app/docker/requirements.allinone.txt /app \
    && python3 -m venv --system-site-packages /opt/dfine-venv \
    && /opt/dfine-venv/bin/python -m pip install --no-cache-dir -r /app/services/layout_analyze/requirements.txt

ENV PORT=8001 OXR_API_HOST=127.0.0.1 OXR_API_PORT=8000 VLLM_PORT=8080 DFINE_PORT=8081 \
    OXR_SERVED_MODEL_NAME=oxr VLLM_GPU_MEMORY_UTILIZATION=0.70 VLLM_MAX_MODEL_LEN=16384 \
    ALLINONE_STARTUP_TIMEOUT=900 DFINE_DEVICE=cuda DFINE_CUDA_GRAPH=1 DFINE_PARALLEL_PREPROCESS=1 \
    OXR__PIPELINE__IMAGE_OUTPUT_DIR=/tmp/oxr-images PYTHONUNBUFFERED=1
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
