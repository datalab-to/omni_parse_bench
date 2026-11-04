# OvisOCR3 as its model card runs it, behind one port: vLLM serves the model, server.py asks it as the card's
# `infer` does and applies the card's post-processing (start.sh). The adapter is providers/ovisocr3.py:
#
#     docker build -t opb-ovisocr3 omni_parse_bench/harness/providers/serve/ovisocr3
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-ovisocr3
#     opb init ovisocr3 > config.yaml
#     opb run --config config.yaml --set system.ovisocr3.base_url=http://localhost:8001
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set OPB_ENDPOINT_KEY
# (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.22.1@sha256:953d3a06d5e64ab582985cd7401289d3abf2a2c14ef2158e9a84313daeec77d7

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: the server runs in a Python of its own, as a user installs a client beside a vLLM server.
RUN /opt/vllm-python -m pip install --no-cache-dir uv && /opt/vllm-python -m uv venv /opt/ovis --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/ovis/bin/python --no-cache httpx==0.28.1

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
