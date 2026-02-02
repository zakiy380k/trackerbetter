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
    # === ПОЛУЧАЕМ ПЕРВИЧНЫЙ СТАТУС (как в main.py) ===
    entity = await client.get_entity(target_id)
    state, last_seen_dt = parse_status(entity)

    if state == "online":
            status_display = "🟢 <b>В сети (Online)</b>"
    elif state.startswith("offline") and last_seen_dt:
        time_str = last_seen_dt.strftime('%H:%M:%S %d.%m')
        status_display = f"🔴 <b>Не в сети</b>\n└ <i>Был онлайн:</i> <code>{time_str}</code>"
    elif state == "offline_recent":
        status_display = "🟠 <b>Не в сети (был недавно)</b>"
    else:
        status_display = "⚪ <b>Статус скрыт</b>"

    previous_status = None          # как в main.py
    online_started_at = None

    start_msg = (
            f"🛰 <b>МОНИТОРИНГ ЗАПУЩЕН</b>\n"
            f"────────────────────\n"
            f"<blockquote>"
            f"👤 <b>Цель:</b> <code>{target_name}</code>\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
            f"📍 <b>Статус:</b> {status_display}"
            f"</blockquote>"
            f"────────────────────\n"
            f"<i>Бот начал наблюдение...</i>"
        )

    # === СТАРТОВОЕ СООБЩЕНИЕ ===
    await notify(owner_id, start_msg)

    # 🔥 фиксируем текущее состояние
    previous_status = state
    online_started_at = time.time() if state == "online" else None

    # === ОСНОВНОЙ ЦИКЛ ===
    while True:
        try:
            entity = await client.get_entity(target_id)
            state, last_seen_dt = parse_status(entity)
            now = datetime.now(LOCAL_TZ)

            # === ЛОГИКА 1:1 КАК В main.py ===
            if state != previous_status:

                # 🟢 ONLINE
                if state == "online":
                    online_started_at = time.time()
                    await notify(
                        owner_id,
                        f"🟢 <b>{target_name} в сети</b>\n"
                        f"⏱ <code>{now.strftime('%H:%M:%S')}</code>"
                    )

                # 🔴 OFFLINE
                elif state.startswith("offline"):
                    duration_text = ""
                    if online_started_at:
                        diff = int(time.time() - online_started_at)
                        minutes, seconds = divmod(diff, 60)
                        duration_text = f"\n⏳ Был в сети: <b>{minutes}м {seconds}с</b>"

                    exit_time = (
                        last_seen_dt.strftime('%H:%M:%S')
                        if last_seen_dt
                        else now.strftime('%H:%M:%S')
                    )

                    msg = (
                        f"🔴 <b>{target_name} вышел</b>\n"
                        f"⏱ <code>{exit_time}</code>"
                        f"{duration_text}"
                    )

                    # микро-онлайн (как в main.py)
                    if online_started_at and diff < 12:
                        msg += "\n⚠️ <i>Микро-онлайн</i>"

                    await notify(owner_id, msg)
                    online_started_at = None

                # 🔥 обновляем состояние
                previous_status = state

            await asyncio.sleep(10)

        except asyncio.CancelledError:
            await notify(owner_id, f"⛔ Трекер остановлен для {target_name}")
            raise

        except Exception as e:
            await notify(
                owner_id,
                f"⚠️ <b>Ошибка трекера:</b>\n<code>{e}</code>"
            )   
            await asyncio.sleep(30)
