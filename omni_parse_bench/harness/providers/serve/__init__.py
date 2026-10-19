"""How each open model is served, one folder per model, to deploy on any GPU host.

    <model>/Dockerfile   the vendor's environment, pinned: base image, packages, repository at a commit
    <model>/start.sh     starts vLLM with the vendor's flags and the weights at a pinned revision, then
                         server.py if there is one; one port out (8001), with /health
    <model>/server.py    for a model whose vendor's code takes part in reading a page (loading the
                         file, preparing the image, asking, retrying, its pipeline or post-processing):
                         that code, per page, behind one route, taking the page file and answering with
                         the vendor's output and the model's raw reply

A model whose vendor offers only the model, with no code of its own around it, has no server.py: its
port is vLLM's /v1, and its adapter asks it directly. Either way, deploying is building
and running the folder's image, then pointing opb at it:

    docker build -t opb-<model> omni_parse_bench/harness/providers/serve/<model>
    docker run --gpus all -p 8001:8001 opb-<model>
    opb benchmark --providers <provider> --options '{"<provider>": {"base_url": "http://<host>:8001"}}'

A server.py stands alone: it imports its vendor's code and what that needs, never omni_parse_bench, so
its image needs this folder and nothing else of the repository; nothing in omni_parse_bench imports
it. So the vendor's code (and its license) stays in its image, and the adapter reading its answer runs
anywhere. With OPB_ENDPOINT_KEY set, it requires that key as a bearer token, and opb sends it.
"""
