# Docling as its vendor runs it, behind one port: server.py runs the `docling` package's DocumentConverter (its
# standard PDF pipeline at its defaults) in uvicorn workers (start.sh). CPU only: no GPU is used. The adapter is
# providers/docling.py:
#
#     docker build -t opb-docling omni_parse_bench/harness/providers/serve/docling
#     docker run -p 8001:8001 opb-docling
#     opb init docling > config.yaml
#     opb run --config config.yaml --set system.docling.base_url=http://localhost:8001
#
# The models its pipeline names (layout, table structure, OCR) are downloaded into the image when it is built, by
# converting one page of text with the same converter the server makes. Each worker loads its own models: where memory is short, set
# fewer workers with WORKERS (docker run -e). Set OPB_ENDPOINT_KEY (docker run -e) to require it as a bearer
# token, as opb sends it.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# Note: the CPU build of torch, as Docling's own container guide installs it; libgl1 and libglib2.0-0 are
# what its OpenCV needs.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        docling==2.153.0 fastapi==0.143.0 uvicorn==0.54.0
ENV PORT=8001 HF_HOME=/opt/hf DOCLING_DEVICE=cpu
COPY server.py start.sh /srv/
# Note: this builds the server's converter (its pinned layout revision) and converts one page of text, so what
# it downloads is what the server loads.
RUN python -c "from PIL import Image, ImageDraw; im = Image.new('RGB', (600, 200), 'white'); \
ImageDraw.Draw(im).text((20, 80), 'Warm up 123', fill='black'); im.save('/tmp/w.png')" \
    && cd /srv && python -c "import server; server.make_converter().convert('/tmp/w.png')" && rm /tmp/w.png
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
