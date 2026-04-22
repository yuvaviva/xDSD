"""Bounded ProcessPoolExecutor helper.

A plain ``ProcessPoolExecutor`` happily accepts an unbounded submission
queue, which is a disaster when you hand it 10,000 channels — the master
process's memory balloons. ``run_pool`` submits at most ``max_inflight``
tasks at a time, keeps the pool fed as workers complete, and yields
results in completion order.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from typing import Callable, Iterable, Iterator, TypeVar

_T = TypeVar("_T")
_R = TypeVar("_R")


def run_pool(func: Callable[[_T], _R], items: Iterable[_T],
             workers: int = 2, max_inflight: int | None = None
             ) -> Iterator[_R]:
    """Run ``func`` over ``items`` on up to ``workers`` processes with
    bounded in-flight submissions.
    """
    if max_inflight is None:
        max_inflight = workers * 2
    it = iter(items)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        in_flight: set[Future] = set()
        try:
            for _ in range(max_inflight):
                nxt = next(it)
                in_flight.add(ex.submit(func, nxt))
        except StopIteration:
            pass
        while in_flight:
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                in_flight.discard(fut)
                try:
                    yield fut.result()
                except Exception as exc:
                    yield exc  # type: ignore[misc]
                try:
                    nxt = next(it)
                    in_flight.add(ex.submit(func, nxt))
                except StopIteration:
                    pass
