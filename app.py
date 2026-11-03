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
    raise ValueError("Не найдены BOT_TOKEN или ANYMODEL_API_KEY")

client = AsyncOpenAI(
    api_key=ANYMODEL_API_KEY,
    base_url="https://anymodel.org/v1",
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- Красивое форматирование чисел (100000 -> 100 000) ----------
def format_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")

# ---------- Сортировка моделей по категориям ----------
def get_model_category(model_id: str) -> str:
    mid = model_id.lower()
    if "gpt" in mid or mid.startswith("o1") or mid.startswith("o3") or "chatgpt" in mid:
        return "🟢 OpenAI"
    if "claude" in mid:
        return "🟠 Anthropic"
    if "gemini" in mid or mid.startswith("ag/"):
        return "🔵 Google"
    if "deepseek" in mid:
        return "🟣 DeepSeek"
    if "llama" in mid or "meta" in mid:
        return "🔴 Meta"
    if "nano-banana" in mid or "flux" in mid or "dalle" in mid or "dall-e" in mid:
        return "🎨 Картинки"
    return "⚪ Прочие"

# ---------- Загрузка и группировка моделей ----------
async def fetch_models_dict():
    try:
        models_response = await client.models.list()
        categories = {}
        for m in models_response.data:
            cat = get_model_category(m.id)
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(m.id)
        return categories
    except Exception as e:
        logging.error(f"Ошибка списка моделей: {e}")
        return None

# ---------- Клавиатура с категориями ----------
async def get_categories_keyboard() -> InlineKeyboardMarkup:
    categories = await fetch_models_dict()
    builder = InlineKeyboardBuilder()
    
    if not categories:
        builder.button(text="❌ Ошибка загрузки моделей", callback_data="none")
        return builder.as_markup()

    for cat in sorted(categories.keys()):
        builder.button(text=cat, callback_data=f"cat:{cat}")
    
    builder.adjust(2)  # По 2 категории в ряд
    return builder.as_markup()

# ---------- Клавиатура со списком моделей внутри категории ----------
async def get_models_keyboard(category: str) -> InlineKeyboardMarkup:
    categories = await fetch_models_dict()
    builder = InlineKeyboardBuilder()
    
    if not categories or category not in categories:
        builder.button(text="❌ Категория не найдена", callback_data="back")
        return builder.as_markup()

    for model_id in categories[category]:
        # Если название модели слишком длинное — обрезаем
        btn_text = model_id if len(model_id) <= 25 else model_id[:22] + "..."
        builder.button(text=btn_text, callback_data=f"model:{model_id}")

    builder.adjust(1)  # Модели в один столбик
    builder.row(InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back"))
    return builder.as_markup()

# ---------- Главное меню ----------
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await db.create_user_if_not_exists(user_id)
    user = await db.get_user(user_id)
    keyboard = await get_categories_keyboard()
    
    text = (
        f"👋 <b>Привет!</b> Я — твой AI-помощник.\n\n"
        f"💳 <b>Твой баланс:</b> {format_num(user['balance'])} токенов\n"
        f"🧠 <b>Текущая модель:</b> <code>{user['model']}</code>\n\n"
        f"👇 Выбери категорию моделей кнопкой ниже:"
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# ---------- Обработка выбора категории ----------
@dp.callback_query(F.data.startswith("cat:"))
async def on_category_select(callback: types.CallbackQuery):
    cat = callback.data.split(":", 1)[1]
    keyboard = await get_models_keyboard(cat)
    await callback.message.edit_text(
        f"📂 <b>Категория:</b> {cat}\n\nВыбери конкретную модель:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Кнопка "Назад" ----------
@dp.callback_query(F.data == "back")
async def on_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    keyboard = await get_categories_keyboard()
    
    text = (
        f"👋 <b>Главное меню</b>\n\n"
        f"💳 <b>Твой баланс:</b> {format_num(user['balance'])} токенов\n"
        f"🧠 <b>Текущая модель:</b> <code>{user['model']}</code>\n\n"
        f"👇 Выбери категорию:"
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ---------- Обработка выбора конкретной модели ----------
@dp.callback_query(F.data.startswith("model:"))
async def on_model_select(callback: types.CallbackQuery):
    model_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    await db.create_user_if_not_exists(user_id)
    await db.set_user_model(user_id, model_id)
    user = await db.get_user(user_id)

    keyboard = await get_categories_keyboard()
    text = (
        f"✅ <b>Модель успешно изменена!</b>\n\n"
        f"🧠 <b>Текущая модель:</b> <code>{model_id}</code>\n"
        f"💳 <b>Твой баланс:</b> {format_num(user['balance'])} токенов\n\n"
        f"Просто напиши свой вопрос в чат 👇"
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("Модель обновлена")

# ---------- Обработка вопросов к нейросети ----------
@dp.message(F.text)
async def handle_question(message: types.Message):
    user_id = message.from_user.id
    await db.create_user_if_not_exists(user_id)
    user = await db.get_user(user_id)

    if user["balance"] <= 0:
        await message.answer("😔 <b>У тебя закончились токены.</b>\n\nПополнение скоро появится, а пока я не могу делать запросы.", parse_mode="HTML")
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
        await message.answer(f"⚠️ Ошибка API: <code>{type(e).__name__}</code>", parse_mode="HTML")
        return

    new_balance = max(0, user["balance"] - spent)
    await db.update_balance(user_id, new_balance)

    for part in split_message(answer_text):
        await message.answer(part)

    await message.answer(
        f"💳 <b>Списано:</b> {format_num(spent)} токенов\n"
        f"💰 <b>Остаток:</b> {format_num(new_balance)} токенов",
        parse_mode="HTML",
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
