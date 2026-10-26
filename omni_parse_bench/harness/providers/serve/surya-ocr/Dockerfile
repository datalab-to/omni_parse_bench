# Surya OCR 2 as the public surya-ocr package runs it, behind one port: vLLM serves the model, server.py
# runs the package's RecognitionPredictor against it (start.sh). The adapter is providers/surya_ocr.py:
#
#     docker build -t opb-surya-ocr omni_parse_bench/harness/providers/serve/surya-ocr
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-surya-ocr
#     opb init surya-ocr > config.yaml
#     opb run --config config.yaml --set system.surya-ocr.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.20.1@sha256:9eff9734a30b6713a8566217d36f8277630fd2d31cec7f0a0292835901a23aa4

RUN apt-get update && apt-get install -y --no-install-recommends curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: the package runs in a Python of its own, its torch the CPU build: the model runs in vLLM, and the
# package only prepares pages and reads replies.
RUN /opt/vllm-python -m pip install --no-cache-dir uv && /opt/vllm-python -m uv venv /opt/surya --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/surya/bin/python --no-cache \
        --index-url https://download.pytorch.org/whl/cpu 'torch==2.14.1+cpu' 'torchvision==0.29.1+cpu' \
    && /opt/vllm-python -m uv pip install --python /opt/surya/bin/python --no-cache surya-ocr==0.22.1

# Note: SURYA_FULLPAGE_REGEN is the package's setting "opt-in for benchmarking" (surya/settings.py): a
# full-page reply that loops or doesn't parse is asked again at rising temperature before block mode.
ENV PORT=8001 SURYA_INFERENCE_URL=http://127.0.0.1:8000/v1 SURYA_INFERENCE_BACKEND=vllm VLLM_GPU_TYPE=h100 \
    SURYA_FULLPAGE_REGEN=true
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
