import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from openai import AsyncOpenAI

import database as db
from utils import split_message

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANYMODEL_API_KEY = os.getenv("ANYMODEL_API_KEY")

if not BOT_TOKEN or not ANYMODEL_API_KEY:
    raise ValueError("Не найдены BOT_TOKEN или ANYMODEL_API_KEY")

client = AsyncOpenAI(
    api_key=ANYMODEL_API_KEY,
    base_url="https://anymodel.org/v1",
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def get_models_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    try:
        models_response = await client.models.list()
        for model in models_response.data:
            builder.button(text=model.id, callback_data=f"model:{model.id}")
        builder.adjust(1)
        return builder.as_markup()
    except Exception as e:
        logging.error(f"Ошибка списка моделей: {e}")
        builder.button(text="gpt-4o (fallback)", callback_data="model:gpt-4o")
        return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await db.create_user_if_not_exists(user_id)
    user = await db.get_user(user_id)
    keyboard = await get_models_keyboard()
    await message.answer(
        f"Привет! Баланс: {user['balance']} токенов.\n"
        f"Модель: <b>{user['model']}</b>\n\n"
        "Выбери модель кнопкой ниже и напиши вопрос.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

@dp.callback_query(F.data.startswith("model:"))
async def on_model_select(callback: types.CallbackQuery):
    model_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    await db.create_user_if_not_exists(user_id)
    await db.set_user_model(user_id, model_id)
    user = await db.get_user(user_id)
    await callback.message.edit_text(
        f"Модель: <b>{model_id}</b>\nБаланс: {user['balance']} токенов.",
        parse_mode="HTML",
    )
    await callback.answer()

@dp.message(F.text)
async def handle_question(message: types.Message):
    user_id = message.from_user.id
    await db.create_user_if_not_exists(user_id)
    user = await db.get_user(user_id)

    if user["balance"] <= 0:
        await message.answer("Токены закончились. Пополнение скоро.")
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        response = await client.chat.completions.create(
            model=user["model"],
            messages=[{"role": "user", "content": message.text.strip()}],
        )
        answer_text = response.choices[0].message.content
        spent = response.usage.total_tokens if response.usage else 100
    except Exception as e:
        logging.exception("Ошибка API")
        await message.answer(f"Ошибка API: <code>{type(e).__name__}</code>", parse_mode="HTML")
        return

    new_balance = max(0, user["balance"] - spent)
    await db.update_balance(user_id, new_balance)

    for part in split_message(answer_text):
        await message.answer(part)

    await message.answer(f"Списано: {spent}. Остаток: <b>{new_balance}</b>", parse_mode="HTML")

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
