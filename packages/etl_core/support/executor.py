"""Lightweight thread-pool executor helper for parallel work."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, List, Tuple, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class ParallelExecutor:
    def __init__(self, max_workers: int) -> None:
        self._max_workers = max_workers

    def map(self, fn: Callable[[T], R], items: Iterable[T]) -> List[R]:
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {executor.submit(fn, item): item for item in items}
            results: List[R] = []
            for future in as_completed(futures):
                results.append(future.result())
            return results

    def submit(self, fn: Callable[..., R], *args: Tuple[object, ...]) -> R:
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future = executor.submit(fn, *args)
            return future.result()
