from __future__ import annotations

from open_notebook.services.events import EventBroker, get_broker
from open_notebook.services.storage import Storage, get_storage


def storage_dep() -> Storage:
    return get_storage()


def broker_dep() -> EventBroker:
    return get_broker()
