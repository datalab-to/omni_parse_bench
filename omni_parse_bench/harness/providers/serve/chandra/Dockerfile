# chandra-ocr-2 as the public chandra-ocr package runs it, behind one port: vLLM serves the model,
# server.py runs the package's steps around it (start.sh). The adapter is providers/chandra_ocr.py:
#
#     docker build -t opb-chandra omni_parse_bench/harness/providers/serve/chandra
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-chandra
#     opb run --system chandra-ocr --options '{"base_url": "http://localhost:8001"}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.17.0@sha256:2296a2a7e1ce1dc59c6577ba5900f4e9910b76c4a0cb134833a8137f92404dfa

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: the package runs in a Python of its own, as a user installs it beside a vLLM server.
RUN /opt/vllm-python -m pip install --no-cache-dir uv && /opt/vllm-python -m uv venv /opt/chandra --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/chandra/bin/python --no-cache httpx==0.28.1 \
        'chandra-ocr @ git+https://github.com/datalab-to/chandra@d4f7467435aa4137d9539f000ddf0b7ced3eb43f'

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
