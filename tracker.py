import asyncio
import time
from datetime import datetime

from utils.telegram import parse_status, resolve_target
from config import LOCAL_TZ


async def run_tracker(
    client,
    target: str,
    owner_id: int,
    notify
):
    # 1. Пытаемся получить entity цели
    entity = await resolve_target(client, target)
    if not entity:
        await notify(owner_id, f"❌ Could not find the target: {target}")
        return

    target_id = entity.id
    target_name = entity.username or entity.first_name or str(target_id)

    await notify(
        owner_id,
        f"🛰 Started tracking {target_name} (ID: {target_id})"
    )

    previous_status = None
    online_started_at = None

    # 2. Основной цикл трекера
    while True:
        try:
            msg = None

            entity = await client.get_entity(target_id)
            state, extra = parse_status(entity)
            now = datetime.now(LOCAL_TZ)

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

                if duration is not None and duration < 12:
                    msg += f"\n⚠️ Micro online session ({duration:.2f}s)"

            # Отправляем уведомление ТОЛЬКО если было событие
            if msg:
                await notify(owner_id, msg)

            previous_status = state

            # Обязательная пауза
            await asyncio.sleep(10)

        except asyncio.CancelledError:
            # Трекер был остановлен
            await notify(owner_id, f"⛔ Tracking stopped for {target_name}")
            raise

        except Exception as e:
            await notify(
                owner_id,
                f"⚠️ Error while tracking {target_name}: {str(e)}"
            )
            await asyncio.sleep(30)
