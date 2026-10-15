# Indra OCR as the `indra-ocr` package runs it, behind one port: server.py reads each page with the
# package's Converter in a pool of single-threaded worker processes, one per core, as its convert_many
# does (start.sh). CPU only: no GPU is used. The adapter is providers/indra_ocr.py:
#
#     docker build -t opb-indra omni_parse_bench/harness/providers/oss/indra
#     docker run -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-indra
#     opb benchmark --providers indra-ocr --options '{"indra-ocr": {"base_url": "http://localhost:8001"}}'
#
# The models the package names download when it starts, into HF_HOME; mount a cache there to keep them.
# Each worker loads its own models (the math models too, math being on by default): where memory is short,
# set fewer workers with WORKERS (docker run -e). Set OPB_ENDPOINT_KEY (docker run -e) to require it as a
# bearer token, as opb sends it.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

RUN pip install --no-cache-dir numpy==2.5.4 opencv-python-headless==5.0.0.93 onnxruntime==1.31.0 \
        pypdfium2==5.14.0 huggingface_hub==2.2.0 indra-ocr==0.3.2

ENV PORT=8001
COPY server.py start.sh /srv/
EXPOSE 8001
ENTRYPOINT ["bash", "/srv/start.sh"]
