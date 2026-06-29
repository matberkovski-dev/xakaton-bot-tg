import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

import database as db

# ---------------------------------------------------------------------------
# НАСТРОЙКИ
# ---------------------------------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "8786689500:AAGb9ivvOSIgIQBcF5zuaT6j3EGahuVquco")

# Telegram user_id организаторов, которые могут смотреть список и делать экспорт
ADMIN_IDS = {
    6616976796,  # Matwey — организатор
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


class AdminDelete(StatesGroup):
    waiting_confirm = State()


class AdminSetTeam(StatesGroup):
    waiting_new_team = State()


class EditSelf(StatesGroup):
    waiting_confirm = State()


class LeaveTeam(StatesGroup):
    waiting_confirm = State()


class KickMember(StatesGroup):
    waiting_confirm = State()


class EditInfo(StatesGroup):
    waiting_choice = State()
    waiting_new_value = State()


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
            f"Если нужно изменить данные — набери /edit.",
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


@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    await state.clear()

    existing = await db.get_participant(message.from_user.id)
    if not existing:
        await message.answer(
            "Ты пока не зарегистрирован(а). Набери /start, чтобы пройти регистрацию."
        )
        return

    await message.answer(
        f"Сейчас у тебя сохранено:\n"
        f"👤 ФИО: <b>{existing['fio']}</b>\n"
        f"🏫 Класс: <b>{existing['school_class']}</b>\n"
        f"📱 Телефон: <b>{existing['phone']}</b>\n"
        f"👥 Команда: <b>{existing['team_name']}</b>\n\n"
        f"Если продолжишь — старые данные удалятся, и я заново задам все вопросы.\n"
        f"Напиши <b>ДА</b>, чтобы перерегистрироваться, или что угодно другое для отмены.",
    )
    await state.set_state(EditSelf.waiting_confirm)


@router.message(EditSelf.waiting_confirm)
async def process_edit_confirm(message: Message, state: FSMContext):
    await state.clear()

    if message.text.strip().upper() != "ДА":
        await message.answer("Хорошо, данные остались без изменений.")
        return

    await db.delete_participant(message.from_user.id)
    await message.answer(
        "Старые данные удалены. Начнём заново 🙂\n\n"
        "Введи своё <b>ФИО</b> полностью:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.waiting_fio)


@router.message(Command("myteam"))
async def cmd_myteam(message: Message):
    me = await db.get_participant(message.from_user.id)
    if not me:
        await message.answer("Ты пока не зарегистрирован(а). Набери /start.")
        return

    members = await db.get_team_members(me["team_name"])
    lines = []
    for m in members:
        mark = "👑 " if m["is_captain"] else "• "
        lines.append(f"{mark}{m['fio']} ({m['school_class']})")

    captain = await db.get_captain(me["team_name"])
    captain_line = "Капитан пока не назначен." if not captain else ""

    await message.answer(
        f"👥 Команда «<b>{me['team_name']}</b>» ({len(members)}/{MAX_TEAM_SIZE}):\n\n"
        + "\n".join(lines)
        + (f"\n\n{captain_line}" if captain_line else "")
    )


@router.message(Command("leaveteam"))
async def cmd_leaveteam(message: Message, state: FSMContext):
    me = await db.get_participant(message.from_user.id)
    if not me:
        await message.answer("Ты пока не зарегистрирован(а). Набери /start.")
        return

    await state.update_data(leave_team_name=me["team_name"])
    await state.set_state(LeaveTeam.waiting_confirm)
    await message.answer(
        f"Точно хочешь выйти из команды «{me['team_name']}»? "
        f"Это полностью удалит твою регистрацию на хакатон — потом нужно будет регистрироваться заново.\n\n"
        f"Напиши <b>ДА</b> для подтверждения или что угодно другое для отмены."
    )


@router.message(LeaveTeam.waiting_confirm)
async def process_leaveteam_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    team_name = data.get("leave_team_name")
    await state.clear()

    if message.text.strip().upper() != "ДА":
        await message.answer("Хорошо, ты остаёшься в команде.")
        return

    await db.remove_from_team(message.from_user.id)
    await message.answer(
        f"Ты вышел(ла) из команды «{team_name}». "
        f"Если захочешь вернуться — набери /start и зарегистрируйся снова."
    )


# ---------------------------------------------------------------------------
# ИНФОРМАЦИЯ О ХАКАТОНЕ
# ---------------------------------------------------------------------------

@router.message(Command("info"))
async def cmd_info(message: Message):
    s = await db.get_all_settings()
    await message.answer(
        "🛠 <b>Инженерный Хакатон</b>\n\n"
        f"📅 Дата и время: <b>{s.get('event_date')}</b>\n"
        f"📍 Место: {s.get('address')}\n\n"
        "Полезные команды: /schedule /rules /whattobring /criteria /prizes /contacts"
    )


@router.message(Command("schedule"))
async def cmd_schedule(message: Message):
    s = await db.get_setting("schedule")
    await message.answer(f"🗓 <b>Программа хакатона:</b>\n\n{s}")


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    s = await db.get_setting("rules")
    await message.answer(f"📜 <b>Правила хакатона:</b>\n\n{s}")


@router.message(Command("whattobring"))
async def cmd_whattobring(message: Message):
    s = await db.get_setting("what_to_bring")
    await message.answer(f"🎒 <b>Что взять с собой:</b>\n\n{s}")


@router.message(Command("criteria"))
async def cmd_criteria(message: Message):
    s = await db.get_setting("criteria")
    await message.answer(f"🏅 <b>Критерии оценки:</b>\n\n{s}")


@router.message(Command("prizes"))
async def cmd_prizes(message: Message):
    s = await db.get_setting("prizes")
    await message.answer(f"🏆 <b>Призы и награды:</b>\n\n{s}")


@router.message(Command("contacts"))
async def cmd_contacts(message: Message):
    s = await db.get_setting("contacts")
    await message.answer(f"📞 <b>Контакты организаторов:</b>\n\n{s}")


@router.message(Command("help"))
async def cmd_help(message: Message):
    is_admin_user = is_admin(message.from_user.id)

    text = (
        "📋 <b>Команды бота</b>\n\n"
        "<b>Регистрация:</b>\n"
        "/start — начать регистрацию\n"
        "/cancel — отменить текущую регистрацию\n"
        "/edit — перерегистрироваться с нуля\n\n"
        "<b>Команда (группа):</b>\n"
        "/myteam — состав своей команды\n"
        "/leaveteam — выйти из команды\n"
        "/kickmember — исключить участника (только для капитана)\n\n"
        "<b>Информация о хакатоне:</b>\n"
        "/info — основная информация\n"
        "/schedule — программа дня\n"
        "/rules — правила\n"
        "/whattobring — что взять с собой\n"
        "/criteria — критерии оценки\n"
        "/prizes — призы\n"
        "/contacts — контакты организаторов\n"
    )

    if is_admin_user:
        text += (
            "\n<b>Админ-команды:</b>\n"
            "/list — список участников\n"
            "/export — выгрузка в CSV\n"
            "/stats — статистика по командам\n"
            "/find ФИО — поиск участника\n"
            "/delete user_id — удалить участника\n"
            "/setteam user_id — сменить команду участника\n"
            "/setcaptain user_id — назначить капитана\n"
            "/editinfo — изменить тексты (/info, /schedule и т.д.)\n"
        )

    await message.answer(text)


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


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return

    query = command.args
    if not query:
        await message.answer("Использование: /find ФИО или часть ФИО\nНапример: /find Иванов")
        return

    results = await db.search_participants(query.strip())
    if not results:
        await message.answer("Никого не нашлось по этому запросу.")
        return

    lines = []
    for p in results:
        lines.append(
            f"<b>{p['fio']}</b> | {p['school_class']} | команда «{p['team_name']}»\n"
            f"📱 {p['phone']} | id: <code>{p['user_id']}</code>"
        )
    await message.answer(
        f"Найдено: {len(results)}\n\n" + "\n\n".join(lines) +
        "\n\nЧтобы удалить участника: /delete user_id\n"
        "Чтобы сменить команду: /setteam user_id"
    )


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "Использование: /delete user_id\n"
            "Сначала найди user_id через /find ФИО"
        )
        return

    target_id = int(command.args.strip())
    participant = await db.get_participant(target_id)
    if not participant:
        await message.answer("Участник с таким user_id не найден.")
        return

    await state.update_data(delete_target_id=target_id, delete_target_fio=participant["fio"])
    await state.set_state(AdminDelete.waiting_confirm)
    await message.answer(
        f"Удалить участника <b>{participant['fio']}</b> "
        f"(команда «{participant['team_name']}»)?\n\n"
        f"Напиши <b>ДА</b> для подтверждения или что угодно другое для отмены.",
    )


@router.message(AdminDelete.waiting_confirm)
async def process_delete_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("delete_target_id")
    target_fio = data.get("delete_target_fio")
    await state.clear()

    if message.text.strip().upper() != "ДА":
        await message.answer("Удаление отменено.")
        return

    deleted = await db.delete_participant(target_id)
    if deleted:
        await message.answer(f"✅ Участник «{target_fio}» удалён из базы.")
    else:
        await message.answer("Не удалось удалить — участник уже отсутствует в базе.")


@router.message(Command("setteam"))
async def cmd_setteam(message: Message, command: CommandObject, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "Использование: /setteam user_id\n"
            "Сначала найди user_id через /find ФИО\n"
            "После этой команды бот спросит название новой команды."
        )
        return

    target_id = int(command.args.strip())
    participant = await db.get_participant(target_id)
    if not participant:
        await message.answer("Участник с таким user_id не найден.")
        return

    await state.update_data(setteam_target_id=target_id, setteam_target_fio=participant["fio"])
    await state.set_state(AdminSetTeam.waiting_new_team)
    await message.answer(
        f"Участник: <b>{participant['fio']}</b>\n"
        f"Текущая команда: «{participant['team_name']}»\n\n"
        f"Введи название новой команды:"
    )


@router.message(AdminSetTeam.waiting_new_team)
async def process_setteam_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("setteam_target_id")
    target_fio = data.get("setteam_target_fio")
    new_team = message.text.strip()
    await state.clear()

    if len(new_team) < 2:
        await message.answer("Название команды слишком короткое. Команда не изменена.")
        return

    updated = await db.change_team(target_id, new_team)
    if updated:
        await message.answer(f"✅ «{target_fio}» теперь в команде «{new_team}».")
    else:
        await message.answer("Не удалось обновить — участник не найден в базе.")


@router.message(Command("setcaptain"))
async def cmd_setcaptain(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return

    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "Использование: /setcaptain user_id\n"
            "Сначала найди user_id через /find ФИО"
        )
        return

    target_id = int(command.args.strip())
    participant = await db.get_participant(target_id)
    if not participant:
        await message.answer("Участник с таким user_id не найден.")
        return

    success = await db.set_captain(participant["team_name"], target_id)
    if success:
        await message.answer(
            f"👑 «{participant['fio']}» назначен(а) капитаном команды «{participant['team_name']}»."
        )
        try:
            await message.bot.send_message(
                target_id,
                f"👑 Тебя назначили капитаном команды «{participant['team_name']}»!\n"
                f"Теперь ты можешь исключать участников из команды через /kickmember.",
            )
        except Exception:
            pass
    else:
        await message.answer("Не удалось назначить капитана — участник не найден в базе.")


@router.message(Command("editinfo"))
async def cmd_editinfo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"editinfo:{key}")]
        for key, label in db.SETTINGS_KEYS.items()
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer("Что хочешь изменить?", reply_markup=kb)
    await state.set_state(EditInfo.waiting_choice)


@router.callback_query(EditInfo.waiting_choice, F.data.startswith("editinfo:"))
async def process_editinfo_choice(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    label = db.SETTINGS_KEYS.get(key, key)
    current_value = await db.get_setting(key)

    await state.update_data(editinfo_key=key, editinfo_label=label)
    await state.set_state(EditInfo.waiting_new_value)

    await callback.message.edit_text(
        f"<b>{label}</b>\n\nТекущее значение:\n{current_value}\n\n"
        f"Отправь новый текст (можно с несколькими строками):"
    )
    await callback.answer()


@router.message(EditInfo.waiting_new_value)
async def process_editinfo_new_value(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("editinfo_key")
    label = data.get("editinfo_label")
    await state.clear()

    new_value = message.text.strip()
    await db.set_setting(key, new_value)
    await message.answer(f"✅ «{label}» обновлено.")


# ---------------------------------------------------------------------------
# КОМАНДЫ КАПИТАНА
# ---------------------------------------------------------------------------

@router.message(Command("kickmember"))
async def cmd_kickmember(message: Message, command: CommandObject, state: FSMContext):
    me = await db.get_participant(message.from_user.id)
    if not me:
        await message.answer("Ты пока не зарегистрирован(а).")
        return

    if not me["is_captain"]:
        await message.answer("Эта команда доступна только капитану команды.")
        return

    if not command.args or not command.args.strip().isdigit():
        members = await db.get_team_members(me["team_name"])
        lines = [f"{m['fio']} — id: <code>{m['user_id']}</code>" for m in members if m["user_id"] != message.from_user.id]
        if not lines:
            await message.answer("В твоей команде больше никого нет.")
            return
        await message.answer(
            "Использование: /kickmember user_id\n\nСостав команды:\n" + "\n".join(lines)
        )
        return

    target_id = int(command.args.strip())

    if target_id == message.from_user.id:
        await message.answer("Себя исключить нельзя — для выхода используй /leaveteam.")
        return

    target = await db.get_participant(target_id)
    if not target or target["team_name"].lower() != me["team_name"].lower():
        await message.answer("Этот человек не состоит в твоей команде.")
        return

    await state.update_data(kick_target_id=target_id, kick_target_fio=target["fio"])
    await state.set_state(KickMember.waiting_confirm)
    await message.answer(
        f"Исключить <b>{target['fio']}</b> из команды «{me['team_name']}»?\n\n"
        f"Напиши <b>ДА</b> для подтверждения или что угодно другое для отмены."
    )


@router.message(KickMember.waiting_confirm)
async def process_kickmember_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("kick_target_id")
    target_fio = data.get("kick_target_fio")
    await state.clear()

    if message.text.strip().upper() != "ДА":
        await message.answer("Исключение отменено.")
        return

    team_name = await db.remove_from_team(target_id)
    if team_name:
        await message.answer(f"✅ «{target_fio}» исключён(а) из команды.")
        try:
            await message.bot.send_message(
                target_id,
                f"Тебя исключили из команды «{team_name}». "
                f"Если хочешь зарегистрироваться в другую команду — набери /start.",
            )
        except Exception:
            pass
    else:
        await message.answer("Не удалось исключить — участник уже отсутствует в базе.")


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
