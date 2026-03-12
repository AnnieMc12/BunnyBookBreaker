"""Thread-safe progress reporting between the converter and GUI."""

import queue
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProgressMessage:
    """Base class for progress messages."""
    pass


@dataclass
class LogMessage(ProgressMessage):
    text: str = ""
    level: str = "info"  # "info", "warn", "error"


@dataclass
class BookStarted(ProgressMessage):
    book_name: str = ""
    book_index: int = 0
    total_books: int = 0


@dataclass
class BookDone(ProgressMessage):
    book_name: str = ""
    success: bool = True


@dataclass
class BatchDone(ProgressMessage):
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: bool = False


class ProgressReporter:
    """Bridges the converter thread and the GUI main thread via a queue."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()

    def log(self, text: str, level: str = "info"):
        self._queue.put(LogMessage(text=text, level=level))

    def book_started(self, book_name: str, index: int, total: int):
        self._queue.put(BookStarted(
            book_name=book_name, book_index=index, total_books=total
        ))

    def book_done(self, book_name: str, success: bool):
        self._queue.put(BookDone(book_name=book_name, success=success))

    def batch_done(self, total: int, succeeded: int, failed: int, cancelled: bool = False):
        self._queue.put(BatchDone(
            total=total, succeeded=succeeded, failed=failed, cancelled=cancelled
        ))

    def get_messages(self) -> list:
        """Drain all pending messages (called by GUI on main thread)."""
        messages = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages
