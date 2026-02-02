import asyncio
import time
from datetime import datetime

from utils.telegram import parse_status
from config import LOCAL_TZ


async def run_tracker(
    client,
    target_id: int,
    target_name: str,
    owner_id: int,
    notify
):
    await notify(
        owner_id,
        f"🛰 Started tracking {target_name} (ID: {target_id})"
    )

    previous_status = None
    online_started_at = None

    while True:
        try:
            entity = await client.get_entity(target_id)
            print(entity)
            state, _ = parse_status(entity)
            now = datetime.now(LOCAL_TZ)

            msg = None

            # ONLINE
            if state == "online" and previous_status != "online":
                online_started_at = time.time()
                msg = (
                    f"🟢 {target_name} is now ONLINE\n"
                    f"⏱ {now.strftime('%Y-%m-%d %H:%M:%S')}"
                )

            # OFFLINE
            elif state.startswith("offline") and previous_status == "online":
                duration = None
                if online_started_at:
                    duration = time.time() - online_started_at

                msg = (
                    f"🔴 {target_name} went OFFLINE\n"
                    f"⏱ {now.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                if duration and duration < 12:
                    msg += f"\n⚠️ Micro session ({duration:.2f}s)"

            if msg:
                await notify(owner_id, msg)

            previous_status = state
            await asyncio.sleep(10)

        except asyncio.CancelledError:
            await notify(owner_id, f"⛔ Tracking stopped for {target_name}")
            raise

        except Exception as e:
            await notify(owner_id, f"⚠️ Tracker error: {e}")
            await asyncio.sleep(30)
