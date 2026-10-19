"""How each open model is served: one folder per model, to deploy on any GPU host.

    <model>/Dockerfile   the vendor's environment, pinned: base image, packages, repository at a commit
    <model>/start.sh     starts vLLM with the vendor's flags and pinned weights, then server.py, if any
    <model>/server.py    the vendor's own code that reads a page, behind one route; a model with no such code
                         has none, and its adapter asks vLLM's /v1 directly

A server.py imports its vendor's code and never omni_parse_bench, so the vendor's code and its license stay
in its image. Each provider's adapter docstring says how to build, run and point opb at it.
"""
