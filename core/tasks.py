import asyncio

_tasks = {}

def start_tracker(user_id: int, coro):
    if user_id in _tasks:
        raise RuntimeError(f"Task already running for user_id: {user_id}")

    task = asyncio.create_task(coro)
    _tasks[user_id] = task
    
def stop_tracker(user_id: int):
    task = _tasks.get(user_id)
    if task:
        task.cancel()
        
def is_tracker_running(user_id: int) -> bool:
    return user_id in _tasks