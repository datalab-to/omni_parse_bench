# Xiaomi whole-page OCR; model and upstream postprocessing revisions are pinned.
FROM vllm/vllm-openai:v0.22.1@sha256:953d3a06d5e64ab582985cd7401289d3abf2a2c14ef2158e9a84313daeec77d7

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
RUN /opt/vllm-python -m pip install --no-cache-dir uv && /opt/vllm-python -m uv venv /opt/client --python 3.12 \
    && /opt/vllm-python -m uv pip install --python /opt/client/bin/python --no-cache httpx==0.28.1

ENV PORT=8001
COPY server.py start.sh /srv/
COPY vendor /srv/vendor
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
