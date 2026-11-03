# app.py
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from openai import AsyncOpenAI

import database as db
from utils import split_message

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANYMODEL_API_KEY = os.getenv("ANYMODEL_API_KEY")

if not BOT_TOKEN or not ANYMODEL_API_KEY:
    raise ValueError("Не найдены токены")

client = AsyncOpenAI(api_key=ANYMODEL_API_KEY, base_url="https://anymodel.org/v1")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def format_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")

# --- Фильтруем картинкогенераторы, чтобы не было ошибок ---
def is_chat_model(model_id: str) -> bool:
    mid = model_id.lower()
    blacklist = ["dall-e", "dalle", "flux", "nano-banana", "stable-diffusion", "whisper", "tts", "vision", "sd-"]
    return not any(x in mid for x in blacklist)

def get_model_category(model_id: str) -> str:
    mid = model_id.lower()
    if "gpt" in mid or mid.startswith(("o1", "o3", "chatgpt")): return "🟢 OpenAI"
    if "claude" in mid: return "🟠 Anthropic"
    if "gemini" in mid or mid.startswith("ag/"): return "🔵 Google"
    if "deepseek" in mid: return "🟣 DeepSeek"
    if "llama" in mid or "meta" in mid: return "🔴 Meta"
    return "⚪ Прочие"

async def fetch_models_dict():
    try:
        models_response = await client.models.list()
        categories = {}
        for m in models_response.data:
            if not is_chat_model(m.id): continue # Пропускаем картинки
            cat = get_model_category(m.id)
            if cat not in categories: categories[cat] = []
            categories[cat].append(m.id)
        return categories
    except Exception:
        return None

# --- Клавиатура главного меню ---
def get_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Сменить модель", callback_data="change_model")
    builder.button(text="💬 Новый диалог", callback_data="new_chat")
    builder.adjust(1)
    return builder.as_markup()

# --- Клавиатура категорий ---
async def get_categories_keyboard() -> InlineKeyboardMarkup:
    categories = await fetch_models_dict()
    builder = InlineKeyboardBuilder()
    if not categories:
        builder.button(text="❌ Ошибка загрузки", callback_data="none")
        return builder.as_markup()
    for cat in sorted(categories.keys()):
        builder.button(text=cat, callback_data=f"cat:{cat}")
    builder.adjust(2)
    return builder.as_markup()

# --- Клавиатура списка моделей ---
async def get_models_keyboard(category: str) -> InlineKeyboardMarkup:
    categories = await fetch_models_dict()
    builder = InlineKeyboardBuilder()
    if categories and category in categories:
        for model_id in categories[category]:
            btn_text = model_id if len(model_id) <= 25 else model_id[:22] + "..."
            builder.button(text=btn_text, callback_data=f"model:{model_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cats"))
    return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await db.create_user_if_not_exists(user_id)
    user = await db.get_user(user_id)
    
    text = (
        f"👋 <b>Привет! Я твой умный AI-бот.</b>\n\n"
        f"🧠 Модель: <code>{user['model']}</code>\n"
        f"💳 Баланс: <b>{format_num(user['balance'])}</b> токенов\n\n"
        f"💡 Просто напиши мне сообщение, и я отвечу. Я помню контекст беседы!"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "new_chat")
async def on_new_chat(callback: types.CallbackQuery):
    await db.clear_history(callback.from_user.id)
    await callback.answer("🧹 Память очищена! Начинаем с чистого листа.", show_alert=True)
    await callback.message.edit_text("Диалог сброшен. О чем поговорим?", reply_markup=get_main_menu())

@dp.callback_query(F.data == "change_model")
async def on_change_model(callback: types.CallbackQuery):
    keyboard = await get_categories_keyboard()
    await callback.message.edit_text("📂 <b>Выбери категорию моделей:</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back_to_cats")
async def on_back_to_cats(callback: types.CallbackQuery):
    keyboard = await get_categories_keyboard()
    await callback.message.edit_text("📂 <b>Выбери категорию моделей:</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def on_category_select(callback: types.CallbackQuery):
    cat = callback.data.split(":", 1)[1]
    keyboard = await get_models_keyboard(cat)
    await callback.message.edit_text(f"📂 <b>{cat}</b>\n\nВыбери модель:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("model:"))
async def on_model_select(callback: types.CallbackQuery):
    model_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    await db.create_user_if_not_exists(user_id)
    await db.set_user_model(user_id, model_id)
    await db.clear_history(user_id) # При смене модели лучше сбросить контекст
    
    user = await db.get_user(user_id)
    text = (
        f"✅ <b>Модель изменена на:</b> <code>{model_id}</code>\n"
        f"💳 <b>Баланс:</b> {format_num(user['balance'])} токенов\n\n"
        f"<i>Память диалога очищена. Пиши свой вопрос!</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer("Успешно!")

@dp.message(F.text)
async def handle_question(message: types.Message):
    user_id = message.from_user.id
    await db.create_user_if_not_exists(user_id)
    user = await db.get_user(user_id)

    if user["balance"] <= 0:
        await message.answer("😔 <b>Токены закончились.</b>", parse_mode="HTML")
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Достаем историю из БД (последние 6 сообщений)
    history = await db.get_history(user_id, limit=6)
    # Добавляем текущее сообщение
    messages_payload = history + [{"role": "user", "content": message.text.strip()}]

    try:
        response = await client.chat.completions.create(
            model=user["model"],
            messages=messages_payload,
        )
        answer_text = response.choices[0].message.content
        spent = response.usage.total_tokens if response.usage else 100
        
        # Сохраняем этот обмен в память
        await db.add_message(user_id, "user", message.text.strip())
        await db.add_message(user_id, "assistant", answer_text)
        
    except Exception as e:
        logging.exception("Ошибка API")
        error_name = type(e).__name__
        if "NotFound" in error_name or "404" in str(e):
            await message.answer("⚠️ Модель не поддерживает чат. Выбери другую через меню.", reply_markup=get_main_menu())
        elif "Authentication" in error_name or "401" in str(e):
            await message.answer("🔑 Ошибка ключа API.")
        else:
            await message.answer(f"❌ Ошибка: <code>{error_name}</code>", parse_mode="HTML")
        return

    new_balance = max(0, user["balance"] - spent)
    await db.update_balance(user_id, new_balance)

    for part in split_message(answer_text):
        await message.answer(part, reply_markup=get_main_menu() if part == split_message(answer_text)[-1] else None)

    await message.answer(
        f"💳 <b>Списано:</b> {format_num(spent)} | <b>Остаток:</b> {format_num(new_balance)}",
        parse_mode="HTML",
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
