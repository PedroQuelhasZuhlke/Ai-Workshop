"""The FastAPI web application: projects, runs, artifacts, approvals.

Not a pipeline stage package. `src/pcbpick/api/orchestrator.py` calls the existing
stage classes directly (see its module docstring) to support the interactive
upload -> mapping confirmation -> requirement resolution -> candidate review ->
plan comparison -> approval -> export flow `docs/roadmap.md`'s M6 describes.
"""
