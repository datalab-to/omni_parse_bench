# dots.mocr as its vendor runs it, behind one port: vLLM serves the model, server.py runs the
# repository's parser around it (start.sh). The adapter is providers/dots.py:
#
#     docker build -t opb-dots omni_parse_bench/harness/providers/serve/dots
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-dots
#     opb benchmark --providers dots-mocr --options '{"dots-mocr": {"base_url": "http://localhost:8001"}}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.17.1@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23

RUN apt-get update && apt-get install -y --no-install-recommends git libcairo2 && rm -rf /var/lib/apt/lists/*
# Note: the Python vLLM is installed in, under a fixed name and by its real path, so start.sh runs it even
# where a host adds a Python of its own (which may take over the `python3` name).
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
RUN /opt/vllm-python -m pip install --no-cache-dir uv \
    && /opt/vllm-python -m uv pip install --python /opt/vllm-python --system --no-cache httpx==0.28.1 pymupdf==1.28.2 cairosvg==2.9.1 requests==2.34.2
RUN git clone -q https://github.com/rednote-hilab/dots.mocr /opt/dots \
    && git -C /opt/dots checkout -q 23f3e5612fb8066d4034d5ecfc8f33a9243533eb

ENV PYTHONPATH=/opt/dots PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
