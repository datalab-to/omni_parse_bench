# Nemotron 3.5 Parse as NVIDIA's own client runs it, behind one port: vLLM serves the model with the
# repository's plugin (one-token MTP, FA3), server.py asks it with the repository's `nemotron_parse`
# client and post-processing (start.sh). The adapter is providers/nemotron_parse.py:
#
#     docker build -t opb-nemotron-parse omni_parse_bench/harness/providers/serve/nemotron_parse
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-nemotron-parse
#     opb benchmark --providers nemotron-parse --options '{"nemotron-parse": {"base_url": "http://localhost:8001"}}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it. The repository's
# code runs in this image; its license is the repository's (OpenMDW-1.1).
# Note: the reference serving contract (docs/serving.md): vLLM 0.26.0, which is also the base of
# NVIDIA's own Dockerfile; this image already has torch 2.11.0 and transformers 5.14.1, as pinned.
FROM vllm/vllm-openai:v0.26.0@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52

ENV REVISION=62cb1e4ba153d113ff64aaf2be6e068c377cf53c
# Note: the repository's source (its plugin, client and post-processing; no weights), installed as its
# model card installs it, held to its pinned inference constraints so vLLM stays at 0.26.0 (less the
# constraints' own pin of the package itself, 3.5.0rc3, an earlier release).
# As NVIDIA's own Dockerfile does, in a venv of its own (the base image's environment fails `pip check`
# by itself, in packages this model doesn't use).
RUN python3 -m venv /opt/nemotron-parse-venv
ENV PATH="/opt/nemotron-parse-venv/bin:$PATH" VIRTUAL_ENV="/opt/nemotron-parse-venv" PYTHONPATH=""
RUN python3 -m pip install --no-cache-dir 'huggingface-hub==1.24.0' \
    && hf download nvidia/Nemotron-3.5-Parse --revision "$REVISION" --local-dir /opt/nemotron-parse \
        --exclude '*.safetensors' --exclude 'reference/parsebench/*' --exclude 'reference/multilingual/*' \
    && grep -v '^nemotron-parse==' /opt/nemotron-parse/reference/parse_3_5/inference.constraints.txt > /tmp/c.txt \
    && python3 -m pip install --no-cache-dir '/opt/nemotron-parse[vllm,client]' -c /tmp/c.txt \
    && python3 -m pip check

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
