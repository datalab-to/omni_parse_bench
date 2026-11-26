# Docling as its vendor runs it, behind one port: server.py runs the `docling` package's DocumentConverter (its
# standard PDF pipeline at its defaults) in uvicorn workers (start.sh). Its models run on Docling's default device,
# `auto`: the GPU when there is one, else the CPU. The adapter is providers/docling.py:
#
#     docker build -t opb-docling omni_parse_bench/harness/providers/serve/docling
#     docker run --gpus all -p 8001:8001 opb-docling     # without --gpus it runs on the CPU
#     opb init docling > config.yaml
#     opb run --config config.yaml --set system.docling.base_url=http://localhost:8001
#
# The models its pipeline names (layout, table structure, OCR) are downloaded into the image when it is built, by
# converting one page of text with the same converter the server makes. Each worker loads its own models: WORKERS
# (docker run -e) sets how many (start.sh has the defaults). DOCLING_DEVICE=cpu (docker run -e) keeps a GPU host on
# the CPU. Set OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer token, as opb sends it.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# Note: torch's CUDA 12.8 build (cu128, the newest torch that has one), which runs on a driver of 570 or later,
# Blackwell (B200) included, and on a host with no GPU, where torch finds no CUDA device and Docling uses the CPU.
# libgl1 and libglib2.0-0 are what its OpenCV needs.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu128 \
        torch==2.11.0+cu128 torchvision==0.26.0+cu128 docling==2.153.0 fastapi==0.143.0 uvicorn==0.54.0
ENV PORT=8001 HF_HOME=/opt/hf
COPY server.py start.sh /srv/
# Note: this builds the server's converter (its pinned layout revision) and converts one page of text, so what
# it downloads is what the server loads.
RUN python -c "from PIL import Image, ImageDraw; im = Image.new('RGB', (600, 200), 'white'); \
ImageDraw.Draw(im).text((20, 80), 'Warm up 123', fill='black'); im.save('/tmp/w.png')" \
    && cd /srv && python -c "import server; server.make_converter().convert('/tmp/w.png')" && rm /tmp/w.png
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
