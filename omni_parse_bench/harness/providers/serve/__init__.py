"""How each open model is served: one folder per model, to deploy on any GPU host.

    <model>/Dockerfile   the vendor's environment, pinned: base image, packages, repository at a commit
    <model>/start.sh     starts vLLM with the vendor's flags and the weights WEIGHTS and REVISION name (by
                         default the pinned ones opb's numbers come from), then server.py, if any
    <model>/server.py    the vendor's own code that reads a page, behind one route; a model with no such code
                         has none, and its adapter asks vLLM's /v1 directly

Every reply says what is served: `"served": {"weights", "revision"}`, the Hugging Face weights start.sh
started vLLM with, so a run records the model that answered whatever started the server; `http.parse`
refuses a reply without it. A model with no server.py is served under the name `<weights>@<revision>`,
which vLLM's /v1/models lists. vLLM serves the weights under a fixed name, so an adapter never names the
weights it asks for.

A server.py imports its vendor's code and never omni_parse_bench, so the vendor's code and its license stay
in its image; it runs there beside the vLLM serving the model (start.sh). With OPB_ENDPOINT_KEY set, a
server requires it as each request's bearer token. Each adapter's docstring says how to build, run and
point opb at its server.
"""
