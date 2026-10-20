# MinerU2.5-Pro as its model card and client run it, behind one port: vLLM serves the model with
# MinerU's logits processor, server.py runs the client's two-step extraction against it (start.sh). The
# adapter is providers/mineru.py:
#
#     docker build -t opb-mineru omni_parse_bench/harness/providers/serve/mineru
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-mineru
#     opb run --system mineru --options '{"base_url": "http://localhost:8001"}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.21.0@sha256:a230095847e93bd4df9888b33dab956fa9504537b828a23657d2b26fed57b5c9

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# Note: one package serves both sides: vLLM loads its logits processor, server.py its client.
RUN /opt/vllm-python -m pip install --no-cache-dir uv \
    && /opt/vllm-python -m uv pip install --python /opt/vllm-python --system --break-system-packages --no-cache \
        mineru-vl-utils==2.0.7 docvortex==0.5.16

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
