# Nanonets-OCR2-3B as its model card runs it: vLLM alone, on one port (start.sh).
# Its client reads a page with one chat call and no code of the vendor's, so opb asks vLLM directly
# (providers/nanonets.py):
#
#     docker build -t opb-nanonets omni_parse_bench/harness/providers/serve/nanonets
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-nanonets
#     opb benchmark --providers nanonets-ocr --options '{"nanonets-ocr": {"base_url": "http://localhost:8001"}}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.17.1@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python

ENV PORT=8001
COPY start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
