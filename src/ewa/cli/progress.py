import builtins
import time
from collections.abc import Iterator
from itertools import batched
from queue import Queue

from rich.progress import Progress, TextColumn, TimeElapsedColumn, BarColumn, MofNCompleteColumn, TaskProgressColumn
from typing import Self, Literal, Iterable, Collection, TypeVar
from types import TracebackType
from ewa.ui import console


T = TypeVar("T")

class DisplayProgress(Progress):
    def __init__(self, *args, **kwargs):
        if not args:
            args = (
                TextColumn("[progress.description]{task.description}"),
                MofNCompleteColumn(),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
            )
        self.builtin_print = builtins.print
        kwargs["console"] = console
        super().__init__(*args, **kwargs)

    def __enter__(self) -> Self:
        builtins.print = self._intercepted_print
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        builtins.print = self.builtin_print
        self.stop()

    @staticmethod
    def _expected_signature(args, kwargs) -> Literal[False] | tuple[str, int, int]:
        if kwargs:
            return False
        if len(args) != 3:
            return False
        task, current, total = args
        if isinstance(task, str) and isinstance(current, int) and isinstance(total, int):
            return task, current, total
        return False

    def _intercepted_print(self, *args, **kwargs):
        expected_signature = self._expected_signature(args, kwargs)
        if not expected_signature:
            return console.print(*args, **kwargs)

        task_name, current, total = expected_signature
        current_task = None

        for task in self.tasks:
            if task_name == task.description:
                current_task = task

        if current_task is None:
            self.add_task(task_name, completed=current, total=total)
            return None

        self.update(current_task.id, completed=current, total=total)
        return None


def track_batch_queue(
    queue: Queue[T], terminator: object, name: str = "queue", batch_size: int = 1000
) -> Iterable[tuple[T]]:
    task_name = f"[cyan]Writing {name}"
    processed = 0
    start_time = time.time()
    print(f"[cyan]Starting processing {name} task")
    for batch in batched(iter(queue.get, terminator), batch_size):
        processed += len(batch)
        yield batch
        print(task_name, processed, processed + queue.qsize())
    print(f"[cyan]Finished processing {name} task in [{time.time() - start_time:>7.2f}s]")


def track_batch_sized(
    collection: Collection[T], name: str = "collection", batch_size: int = 100
) -> Iterable[tuple[T, ...]]:
    task_name = f"[cyan]Writing {name}"
    processed = 0
    total = len(collection)
    start_time = time.time()
    print(f"[cyan]Starting processing {name} task")
    for batch in batched(collection, batch_size):
        processed += len(batch)
        yield batch
        print(task_name, processed, total)
    print(f"[cyan]Finished processing {name} task in [{time.time() - start_time:>7.2f}s]")


def track_sized(collection: Collection[T], name: str = "collection") -> Iterable[T]:
    task_name = f"[cyan]Processing {name}"
    total = len(collection)
    for i, item in enumerate(collection):
        yield item
        print(task_name, i+1, total)


def track_unknown(iterator: Iterator[T], name: str = "collection", total: int = 0) -> Iterator[T]:
    task_name = f"[cyan]Processing {name}"
    for i, item in enumerate(iterator):
        yield item
        print(task_name, i+1, total)
