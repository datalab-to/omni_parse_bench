# Infinity-Parser2 (Pro or Flash) as its SDK runs it, behind one port: vLLM serves the model, server.py
# asks it as the `infinity_parser2` SDK's vLLM backends do and reads the reply with the SDK's own
# post-processing (start.sh). The adapter is providers/infinity.py:
#
#     docker build -t opb-infinity-parser2 omni_parse_bench/harness/providers/serve/infinity-parser2
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-infinity-parser2
#     opb init infinity-parser2 > config.yaml
#     opb run --config config.yaml --set system.infinity-parser2.base_url=http://localhost:8001
#
# WEIGHTS picks the model (docker run -e WEIGHTS=infly/Infinity-Parser2-Flash; Pro by default, which needs
# two GPUs); REVISION its checkpoint (start.sh pins each). The weights download when it starts, into
# HF_HOME; mount a cache there to keep them. Set OPB_ENDPOINT_KEY (docker run -e) to require it as a
# bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.17.1@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: the model card's vLLM needs transformers 5.3.0. The SDK runs in a Python of its own without
# torch, as a client beside a vLLM server installs it.
RUN /opt/vllm-python -m pip install --no-cache-dir uv \
    && /opt/vllm-python -m uv pip install --python /opt/vllm-python --system --break-system-packages --no-cache \
        transformers==5.3.0 \
    && /opt/vllm-python -m uv venv /opt/infinity --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/infinity/bin/python --no-cache httpx==0.28.1 infinity_parser2==0.4.0

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
