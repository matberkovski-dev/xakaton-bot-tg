import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    FSInputFile,
)

import database as db

# ---------------------------------------------------------------------------
# НАСТРОЙКИ
# ---------------------------------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН")

# Telegram user_id организаторов, которые могут смотреть список и делать экспорт
ADMIN_IDS = {
    # 123456789,  # <-- замени на свой user_id (узнать его можно через @userinfobot)
}

MAX_TEAM_SIZE = 5  # максимум участников в команде

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()


# ---------------------------------------------------------------------------
# СОСТОЯНИЯ (ШАГИ РЕГИСТРАЦИИ)
# ---------------------------------------------------------------------------

class Registration(StatesGroup):
    waiting_fio = State()
    waiting_class = State()
    waiting_phone = State()
    waiting_team_choice = State()   # создать команду / вступить в команду
    waiting_team_name_new = State()
    waiting_team_name_join = State()
    confirm = State()


# ---------------------------------------------------------------------------
# КЛАВИАТУРЫ
# ---------------------------------------------------------------------------

def team_choice_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Создать новую команду")],
            [KeyboardButton(text="Вступить в существующую")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def confirm_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подтвердить")],
            [KeyboardButton(text="❌ Начать заново")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------------------------------------------------------------------------
# СТАРТ / ОТМЕНА
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    existing = await db.get_participant(message.from_user.id)
    if existing:
        await message.answer(
            f"Привет, {existing['fio']}! Ты уже зарегистрирован(а) на хакатон ✅\n"
            f"Команда: <b>{existing['team_name']}</b>\n\n"
            f"Если нужно всё изменить — набери /cancel, затем /start заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer(
        "👋 Привет! Это бот регистрации на <b>Инженерный Хакатон</b>.\n\n"
        "Сейчас задам несколько вопросов — это займёт пару минут.\n\n"
        "Для отмены в любой момент набери /cancel.\n\n"
        "Введи своё <b>ФИО</b> полностью:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.waiting_fio)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Регистрация отменена. Набери /start, чтобы начать заново.",
                          reply_markup=ReplyKeyboardRemove())


# ---------------------------------------------------------------------------
# ШАГ 1: ФИО
# ---------------------------------------------------------------------------

@router.message(Registration.waiting_fio)
async def process_fio(message: Message, state: FSMContext):
    fio = message.text.strip()
    if len(fio.split()) < 2 or len(fio) < 5:
        await message.answer("Похоже, это не похоже на полное ФИО. Введи, пожалуйста, "
                              "Фамилию Имя (и Отчество), например: Иванов Иван")
        return

    await state.update_data(fio=fio)
    await message.answer("Отлично! Теперь укажи свой <b>класс</b> (например: 9Б):")
    await state.set_state(Registration.waiting_class)


# ---------------------------------------------------------------------------
# ШАГ 2: КЛАСС
# ---------------------------------------------------------------------------

@router.message(Registration.waiting_class)
async def process_class(message: Message, state: FSMContext):
    await state.update_data(school_class=message.text.strip())
    await message.answer(
        "Теперь поделись номером телефона для связи — нажми кнопку ниже "
        "или просто напиши номер вручную:",
        reply_markup=phone_kb(),
    )
    await state.set_state(Registration.waiting_phone)


# ---------------------------------------------------------------------------
# ШАГ 3: ТЕЛЕФОН
# ---------------------------------------------------------------------------

@router.message(Registration.waiting_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await ask_team_choice(message, state)


@router.message(Registration.waiting_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    if len(phone) < 5:
        await message.answer("Это не похоже на номер телефона. Попробуй ещё раз:")
        return
    await state.update_data(phone=phone)
    await ask_team_choice(message, state)


async def ask_team_choice(message: Message, state: FSMContext):
    await message.answer(
        "Теперь о команде 👥\nУ вас уже есть команда, или нужно создать новую?",
        reply_markup=team_choice_kb(),
    )
    await state.set_state(Registration.waiting_team_choice)


# ---------------------------------------------------------------------------
# ШАГ 4: ВЫБОР КОМАНДЫ
# ---------------------------------------------------------------------------

@router.message(Registration.waiting_team_choice, F.text == "Создать новую команду")
async def choose_create_team(message: Message, state: FSMContext):
    await message.answer(
        "Введи название новой команды:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.waiting_team_name_new)


@router.message(Registration.waiting_team_choice, F.text == "Вступить в существующую")
async def choose_join_team(message: Message, state: FSMContext):
    teams = await db.get_team_names()
    if not teams:
        await message.answer(
            "Пока не создано ни одной команды. Хочешь создать новую?",
            reply_markup=team_choice_kb(),
        )
        return

    teams_list = "\n".join(f"• {t['team_name']} ({t['members_count']}/{MAX_TEAM_SIZE})" for t in teams)
    await message.answer(
        f"Существующие команды:\n{teams_list}\n\nВведи название команды, к которой хочешь присоединиться:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.waiting_team_name_join)


@router.message(Registration.waiting_team_choice)
async def team_choice_invalid(message: Message):
    await message.answer("Пожалуйста, выбери один из вариантов на клавиатуре 👇",
                          reply_markup=team_choice_kb())


# ---------------------------------------------------------------------------
# ШАГ 5а: НОВАЯ КОМАНДА
# ---------------------------------------------------------------------------

@router.message(Registration.waiting_team_name_new)
async def process_team_name_new(message: Message, state: FSMContext):
    team_name = message.text.strip()

    if len(team_name) < 2:
        await message.answer("Название команды слишком короткое. Попробуй ещё раз:")
        return

    if await db.team_exists(team_name):
        await message.answer(
            "Команда с таким названием уже существует. Выбери другое название, "
            "либо вернись назад и выбери «Вступить в существующую»:"
        )
        return

    await state.update_data(team_name=team_name)
    await show_confirmation(message, state)


# ---------------------------------------------------------------------------
# ШАГ 5б: ВСТУПЛЕНИЕ В КОМАНДУ
# ---------------------------------------------------------------------------

@router.message(Registration.waiting_team_name_join)
async def process_team_name_join(message: Message, state: FSMContext):
    team_name = message.text.strip()

    if not await db.team_exists(team_name):
        await message.answer(
            "Такой команды не нашлось. Проверь название и попробуй снова, "
            "либо набери /cancel и начни заново, чтобы создать новую команду."
        )
        return

    count = await db.get_team_members_count(team_name)
    if count >= MAX_TEAM_SIZE:
        await message.answer(
            f"В команде «{team_name}» уже максимум участников ({MAX_TEAM_SIZE}). "
            "Выбери другую команду или создай новую: /cancel, затем /start."
        )
        return

    await state.update_data(team_name=team_name)
    await show_confirmation(message, state)


# ---------------------------------------------------------------------------
# ПОДТВЕРЖДЕНИЕ
# ---------------------------------------------------------------------------

async def show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    text = (
        "Проверь свои данные:\n\n"
        f"👤 ФИО: <b>{data['fio']}</b>\n"
        f"🏫 Класс: <b>{data['school_class']}</b>\n"
        f"📱 Телефон: <b>{data['phone']}</b>\n"
        f"👥 Команда: <b>{data['team_name']}</b>\n\n"
        "Всё верно?"
    )
    await message.answer(text, reply_markup=confirm_kb())
    await state.set_state(Registration.confirm)


@router.message(Registration.confirm, F.text == "✅ Подтвердить")
async def process_confirm(message: Message, state: FSMContext):
    data = await state.get_data()

    await db.add_participant(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        fio=data["fio"],
        school_class=data["school_class"],
        phone=data["phone"],
        team_name=data["team_name"],
        registered_at=datetime.now().isoformat(timespec="seconds"),
    )

    await message.answer(
        "🎉 Регистрация завершена! До встречи на хакатоне.\n\n"
        "Если нужно изменить данные — напиши организаторам.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()

    # уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"✅ Новая регистрация:\n{data['fio']} ({data['school_class']}) — команда «{data['team_name']}»",
            )
        except Exception:
            pass


@router.message(Registration.confirm, F.text == "❌ Начать заново")
async def process_restart(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Хорошо, начнём заново. Набери /start.", reply_markup=ReplyKeyboardRemove())


@router.message(Registration.confirm)
async def confirm_invalid(message: Message):
    await message.answer("Пожалуйста, используй кнопки ниже 👇", reply_markup=confirm_kb())


# ---------------------------------------------------------------------------
# АДМИНСКИЕ КОМАНДЫ
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message.from_user.id):
        return

    participants = await db.get_all_participants()
    if not participants:
        await message.answer("Пока никто не зарегистрирован.")
        return

    lines = []
    for p in participants:
        lines.append(
            f"{p['fio']} | {p['school_class']} | {p['team_name']} | {p['phone']} | @{p['username'] or '—'}"
        )
    text = f"Всего зарегистрировано: {len(participants)}\n\n" + "\n".join(lines)

    # Telegram ограничивает длину сообщения 4096 символами
    for i in range(0, len(text), 4000):
        await message.answer(text[i:i + 4000])


@router.message(Command("export"))
async def cmd_export(message: Message):
    if not is_admin(message.from_user.id):
        return

    path = await db.export_to_csv()
    await message.answer_document(FSInputFile(path), caption="Список участников (CSV)")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    total = await db.count_participants()
    teams = await db.get_team_names()
    teams_text = "\n".join(f"• {t['team_name']}: {t['members_count']} чел." for t in teams)
    await message.answer(f"👥 Участников: {total}\n🏆 Команд: {len(teams)}\n\n{teams_text}")


# ---------------------------------------------------------------------------
# ТОЧКА ВХОДА
# ---------------------------------------------------------------------------

async def main():
    await db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
