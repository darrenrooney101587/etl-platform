"""Lightweight thread-pool executor helper for parallel work."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Callable, Iterable, List, Optional, Tuple, TypeVar
import logging

T = TypeVar("T")
R = TypeVar("R")

logger = logging.getLogger(__name__)


class ParallelExecutor:
    """Thread-pool executor for parallel task execution.

    Supports two modes:
    - `map`: blocks until all tasks complete (for batch-style processing)
    - `submit_all`: fire-and-forget style; tasks run independently and don't
      block each other. Slow tasks won't prevent new tasks from starting.
    """

    def __init__(self, max_workers: int) -> None:
        self._max_workers = max_workers

    def map(self, fn: Callable[[T], R], items: Iterable[T]) -> List[R]:
        """Execute fn for each item in parallel, blocking until all complete.

        Use this when you need all results before proceeding.
        """
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {executor.submit(fn, item): item for item in items}
            results: List[R] = []
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.error("Task failed: %s", exc)
            return results

    def submit_all(
        self,
        fn: Callable[[T], R],
        items: Iterable[T],
        on_complete: Optional[Callable[[T, Optional[R], Optional[Exception]], None]] = None,
    ) -> List[Future[R]]:
        """Submit all tasks without blocking. Returns list of futures.

        Args:
            fn: Function to execute for each item.
            items: Iterable of items to process.
            on_complete: Optional callback invoked when each task completes.
                         Signature: (item, result, exception) -> None

        This is ideal for long-running tasks where you don't want slow items
        to block faster ones. The thread pool manages concurrency; as workers
        become available, they pick up the next pending task.
        """
        executor = ThreadPoolExecutor(max_workers=self._max_workers)
        futures: List[Future[R]] = []
        item_map: dict[Future[R], T] = {}

        for item in items:
            future = executor.submit(fn, item)
            futures.append(future)
            item_map[future] = item

            if on_complete:
                def make_callback(f: Future[R], it: T) -> Callable[..., None]:
                    def callback(fut: Future[R]) -> None:
                        try:
                            result = fut.result()
                            on_complete(it, result, None)
                        except Exception as exc:
                            on_complete(it, None, exc)
                    return callback

                future.add_done_callback(make_callback(future, item))

        # Don't call executor.shutdown() here; let futures complete asynchronously
        # The executor will clean up when the process exits or when all futures resolve

        return futures

    def submit(self, fn: Callable[..., R], *args: Tuple[object, ...]) -> R:
        """Submit a single task and block until it completes."""
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future = executor.submit(fn, *args)
            return future.result()

    def wait_for_all(self, futures: List[Future[R]], timeout: Optional[float] = None) -> List[R]:
        """Wait for all futures to complete and return results.

        Args:
            futures: List of futures from submit_all.
            timeout: Optional timeout in seconds.

        Returns:
            List of results (may contain None for failed tasks).
        """
        results: List[R] = []
        for future in as_completed(futures, timeout=timeout):
            try:
                results.append(future.result())
            except Exception as exc:
                logger.error("Task failed during wait: %s", exc)
        return results
