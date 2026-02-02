from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently
)
from config import LOCAL_TZ, UTC_TZ


async def resolve_target(client, target: str):
    if client is None:
        print("DEBUG: resolve_target received None instead of client!")
        return None
    try:
        

        if target.startswith("@"):
            target = target[1:]

        if target.isdigit():
            return await client.get_entity(int(target))

        return await client.get_entity(target)

    except Exception as e:
        print(f"DEBUG: Resolve target error: {e}") # Это поможет понять причину
        return None

def convert_utc_to_local(dt):
    if dt.tzinfo is None:
        dt = UTC_TZ.localize(dt)
    return dt.astimezone(LOCAL_TZ)


def parse_status(entity):
    status = entity.status

    if isinstance(status, UserStatusOnline):
        return "online", None

    if isinstance(status, UserStatusOffline):
        local_time = convert_utc_to_local(status.was_online)
        return "offline", local_time

    if isinstance(status, UserStatusRecently):
        return "recently", None

    return "unknown", None
