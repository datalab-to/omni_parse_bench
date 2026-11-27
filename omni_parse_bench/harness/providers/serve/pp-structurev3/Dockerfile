# PP-StructureV3 as PaddleOCR documents it, behind one port: server.py runs PaddleOCR's own `PPStructureV3`
# pipeline (layout, OCR, table, formula and seal models) in uvicorn workers (start.sh). It runs on the CPU
# here; a GPU is optional. The adapter is providers/pp_structurev3.py:
#
#     docker build -t opb-pp-structurev3 omni_parse_bench/harness/providers/serve/pp-structurev3
#     docker run -p 8001:8001 opb-pp-structurev3
#     opb init pp-structurev3 > config.yaml
#     opb run --config config.yaml --set system.pp-structurev3.base_url=http://localhost:8001
#
# The pipeline's models are in the image, each at the exact Hugging Face commit model_pins.py names, so the
# server downloads nothing. Each worker loads its own models: where memory is short, set fewer workers with
# WORKERS (docker run -e). Set OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# Note: libgl1, libglib2.0-0 and libgomp1 are what paddlepaddle and OpenCV need.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
# Paddle#77340: paddlepaddle 3.3.1's oneDNN+PIR regression crashes the Linux CPU server; pin 3.2.2.
RUN pip install --no-cache-dir paddlepaddle==3.2.2 'paddleocr[doc-parser]==3.7.0' fastapi==0.143.0 uvicorn==0.54.0

# Note: PaddleX looks for a model in official_models/ under PADDLE_PDX_CACHE_HOME before it downloads it, so the
# pinned commits are put there; PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK skips PaddleX's connectivity check.
ENV PORT=8001 PADDLE_PDX_CACHE_HOME=/opt/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
COPY model_pins.py pin_models.py /srv/
RUN cd /srv && python pin_models.py
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
