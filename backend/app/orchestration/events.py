"""In-process event bus for SSE progress streaming (dev/single-node).

Multi-node deployments should replace this with a Redis pub/sub channel; the
consumer API stays the same.
"""
import queue
import threading
from collections import defaultdict

_lock = threading.Lock()
_channels: dict[str, list[queue.Queue]] = defaultdict(list)


def publish(job_id: str, event: dict) -> None:
    with _lock:
        subscribers = list(_channels.get(job_id, []))
    for q in subscribers:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass


def subscribe(job_id: str) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=2000)
    with _lock:
        _channels[job_id].append(q)
    return q


def unsubscribe(job_id: str, q: queue.Queue) -> None:
    with _lock:
        try:
            _channels[job_id].remove(q)
        except ValueError:
            pass
        if not _channels.get(job_id):
            _channels.pop(job_id, None)
