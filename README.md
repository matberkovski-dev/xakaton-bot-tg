# Бот регистрации на Инженерный Хакатон

Telegram-бот на aiogram 3.x для регистрации участников хакатона с привязкой к командам.

## Возможности

- Пошаговая регистрация (FSM): ФИО → класс → телефон → команда
- Создание новой команды или вступление в существующую
- Ограничение размера команды (по умолчанию 5 человек, меняется в `bot.py`)
- Проверка, что человек не регистрируется дважды
- Подтверждение данных перед сохранением
- Админ-команды: `/list`, `/export` (CSV), `/stats`
- Хранение данных в SQLite (`hackathon.db`)

## Установка и запуск

### 1. Получи токен бота

Напиши [@BotFather](https://t.me/BotFather) в Telegram:
```
/newbot
```
Следуй инструкциям, в конце получишь токен вида `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`.

### 2. Узнай свой user_id (чтобы стать админом)

Напиши [@userinfobot](https://t.me/userinfobot) — он пришлёт твой ID.

### 3. Установи зависимости

```bash
cd hackathon_bot
python3 -m venv venv
source venv/bin/activate        # на Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Настрой бота

Открой `bot.py` и впиши:

```python
BOT_TOKEN = "твой_токен_от_BotFather"

ADMIN_IDS = {
    123456789,  # твой user_id
}
```

Либо (более безопасный способ) задай токен через переменную окружения:

```bash
export BOT_TOKEN="твой_токен"   # Windows: set BOT_TOKEN=твой_токен
```

### 5. Запусти бота

```bash
python3 bot.py
```

Если всё ок, в консоли появится `Бот запущен`. Теперь найди своего бота в Telegram и напиши `/start`.

## Структура проекта

```
hackathon_bot/
├── bot.py              # основная логика бота, FSM-диалог
├── database.py         # работа с SQLite
├── requirements.txt    # зависимости
├── hackathon.db         # база создаётся автоматически при первом запуске
└── README.md
```

## Команды бота

| Команда   | Кто использует | Описание                                  |
|-----------|-----------------|--------------------------------------------|
| `/start`  | все            | начать/повторно открыть регистрацию       |
| `/cancel` | все            | отменить текущую регистрацию              |
| `/list`   | админы         | список всех зарегистрированных            |
| `/export` | админы         | выгрузка списка в CSV-файл                |
| `/stats`  | админы         | статистика по командам                    |

## Как настроить под себя

- **Изменить вопросы регистрации** — в `bot.py` добавь/убери `State` в классе `Registration` и соответствующие хендлеры по аналогии с существующими.
- **Изменить максимальный размер команды** — переменная `MAX_TEAM_SIZE` в начале `bot.py`.
- **Подключить к существующему Flask-проекту "Инженерный Хакатон"** — вместо отдельной SQLite-базы можно писать прямо в ту же БД, что использует Flask-приложение (если структура таблиц совместима), либо дёргать Flask API из бота через `aiohttp`.

## Деплой на сервер (чтобы бот работал 24/7)

Самый простой вариант — небольшой VPS (например, от 150₍/мес) с systemd-сервисом:

```ini
# /etc/systemd/system/hackathon-bot.service
[Unit]
Description=Hackathon Registration Bot
After=network.target

[Service]
WorkingDirectory=/path/to/hackathon_bot
ExecStart=/path/to/hackathon_bot/venv/bin/python3 bot.py
Restart=always
Environment="BOT_TOKEN=твой_токен"

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable hackathon-bot
sudo systemctl start hackathon-bot
```
