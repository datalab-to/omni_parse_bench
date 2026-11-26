# OCRia-1 as its model card runs it: vLLM alone, on one port (start.sh). Its card documents one chat call per
# page, so opb asks vLLM directly (providers/ocria_1.py):
#
#     docker build -t opb-ocria-1 omni_parse_bench/harness/providers/serve/ocria-1
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-ocria-1
#     opb init ocria-1 > config.yaml
#     opb run --config config.yaml --set system.ocria-1.base_url=http://localhost:8001
#
# The card's layout boxes (experimental) are a second server in the same image, boxes.sh on port 8100, for
# blocks with the adapter's `layout` option:
#
#     docker run --gpus all -p 8100:8100 -v ~/.cache/huggingface:/root/.cache/huggingface \
#         --entrypoint bash opb-ocria-1 /srv/boxes.sh
#     opb run --config config.yaml --set system.ocria-1.base_url=http://localhost:8001 \
#         --set system.ocria-1.layout=true --set system.ocria-1.grounding_url=http://localhost:8100
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
#
# The model card: "Serve with vLLM 0.30 or later. vLLM compiles kernels for this architecture at start-up and
# needs the CUDA toolkit (nvcc); the vllm/vllm-openai Docker image has it." This is its 0.30.0 release.
#
# OCRia-1 is licensed under the OCRia-1 Model and Code License (a modified OpenRAIL-M; LlamaIndex, Inc.),
# https://huggingface.co/llamaindex/OCRia-1/blob/main/LICENSE. This folder holds none of its weights or code.
FROM vllm/vllm-openai:v0.30.0@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(python3 -c 'import os, sys, vllm; print(os.path.realpath(sys.executable))')" /opt/vllm-python
# The box server's venv (boxes.sh): the card's Transformers 5.22.2 over the image's torch and torchvision.
COPY no-torch.txt /srv/no-torch.txt
RUN curl -LsSf https://astral.sh/uv/0.13.5/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv venv /opt/boxes --python /opt/vllm-python --system-site-packages \
    && uv pip install --python /opt/boxes/bin/python --override /srv/no-torch.txt \
        transformers==5.22.2 accelerate==1.16.0 timm==1.0.31 \
        scipy==1.18.1 pypdfium2==5.13.0 huggingface_hub==2.5.0

ENV PORT=8001
COPY start.sh boxes.sh boxes.py /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
