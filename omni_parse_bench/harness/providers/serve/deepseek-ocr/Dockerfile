# DeepSeek-OCR-2 as its repository runs it: its own vLLM 0.8.5 setup (V0 engine, the repository's model
# code), wrapped by server.py in one HTTP route. The adapter is providers/deepseek_ocr.py:
#
#     docker build -t opb-deepseek-ocr omni_parse_bench/harness/providers/serve/deepseek-ocr
#     docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-deepseek-ocr
#     opb run --system deepseek-ocr --options '{"base_url": "http://localhost:8001"}'
#
# The weights download when it starts, into HF_HOME; mount a cache there to keep them. Set
# OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM vllm/vllm-openai:v0.8.5@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
# Note: the packages and flash-attention build the repository's README installs beside vLLM 0.8.5.
RUN PIP_BREAK_SYSTEM_PACKAGES=1 /usr/bin/python3 -m pip install --no-cache-dir -q transformers==4.46.3 \
        tokenizers==0.20.3 einops==0.8.2 easydict==1.13 addict==2.4.0 PyMuPDF==1.28.2 img2pdf==0.6.3 \
    && PIP_BREAK_SYSTEM_PACKAGES=1 /usr/bin/python3 -m pip install --no-cache-dir -q \
        https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.3/flash_attn-2.7.3+cu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl
RUN git clone -q https://github.com/deepseek-ai/DeepSeek-OCR-2 /opt/dsocr2 \
    && git -C /opt/dsocr2 checkout -q 2f3699ebbb96fa8af32212e8c170f2cc28730fad
# Note: config.py is where the repository says to set the model's path; it reads the weights start.sh
# fetches (WEIGHTS at REVISION, the pinned ones by default).
RUN sed -i "s|^MODEL_PATH = .*|import os; MODEL_PATH = os.environ['DEEPSEEK_WEIGHTS']|" \
        /opt/dsocr2/DeepSeek-OCR2-master/DeepSeek-OCR2-vllm/config.py

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
