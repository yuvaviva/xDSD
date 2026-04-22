"""Orchestration helpers: bounded ProcessPoolExecutor + pipeline wrappers."""

# `pool` is leaf-level safe; `pipeline` pulls from every stage and would
# create a circular import if we eagerly re-exported it here. Use the full
# path: ``from wbdec.orchestrate.pipeline import run_pipeline``.
from .pool import run_pool

__all__ = ["run_pool"]
