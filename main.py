import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    webhook_url = "https://trackerbetter.onrender.com/webhook"
    await bot.set_webhook(webhook_url)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"ok": True}
