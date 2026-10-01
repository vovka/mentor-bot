"""The pending morning check-in in state.json: {"date", "stage", "message_id", ...}."""

from mentor.adapters.store.lock import locked


def save(store, checkin: dict | None) -> None:
    with locked(store.data_dir):
        state = store.read_state()
        state.pop("checkin", None)
        if checkin:
            state["checkin"] = checkin
        store.write_state(state)


def claim(store, stages: set[str], message_id: int | None = None) -> dict | None:
    """Atomically move a check-in in one of `stages` to "working" so a job and a button can't both act."""
    with locked(store.data_dir):
        state = store.read_state()
        checkin = state.get("checkin") or {}
        if checkin.get("stage") not in stages:
            return None
        if message_id is not None and checkin.get("message_id") != message_id:
            return None
        state["checkin"] = {**checkin, "stage": "working"}
        store.write_state(state)
        return checkin
