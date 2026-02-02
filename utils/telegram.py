from telethon.tl.types import (UserStatusOnline,
                                UserStatusOffline,
                                    UserStatusRecently)
from config import LOCAL_TZ, UTC_TZ

async def resolve_target(client, target):
    try:
        if target.isdigit():
            return await client.get_entity(int(target))
        return await client.get_entity(target.lstrip('@'))
    except Exception:
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
        return "offline_recent", None

    return "unknown", None
