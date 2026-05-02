from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from open_notebook.services.storage import Storage


class EventBroker:
    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(
        self,
        storage: Storage,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        storage.add_event(job_id, event_type, payload)
        for queue in list(self._queues.get(job_id, [])):
            await queue.put({"type": event_type, "payload": payload})

    async def subscribe(self, job_id: str):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[job_id].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues[job_id].remove(queue)


_broker = EventBroker()


def get_broker() -> EventBroker:
    return _broker
