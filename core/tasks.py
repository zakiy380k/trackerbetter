import asyncio

_tasks = {}


def start_tracker(user_id: int, coro):
    if user_id in _tasks:
        raise RuntimeError("Tracker already running")

    task = asyncio.create_task(coro)
    _tasks[user_id] = task


def stop_tracker(user_id: int):
    task = _tasks.pop(user_id, None)
    if task:
        task.cancel()


def is_tracker_running(user_id: int) -> bool:
    return user_id in _tasks
