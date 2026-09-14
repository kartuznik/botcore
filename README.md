# botcore

Каркас Telegram-бота на **aiogram 3** и **Python 3.11+**. Здесь только швы: конфиг, логирование,
реестр модулей, хранилище, middleware и composition root. Бизнес-логики нет — кроме модуля
`health`, который доказывает, что проводка работает.

## Структура

```
core/
  __main__.py       # точка входа: python -m core
  app.py            # BotApp — composition root (middleware, модули, polling, shutdown)
  config.py         # чтение env, fail-fast без трейса
  logging_setup.py  # единый формат логов с именем модуля
  middleware.py     # логирование апдейтов + глобальный перехват исключений
  registry.py       # реестр: имя модуля -> фабрика Router
  storage.py        # StorageInterface (Protocol) + SqliteStorage
modules/
  health.py         # /start, /help, вежливый ответ на неизвестное
tests/              # pytest + pytest-asyncio
```

## Переменные окружения

| Переменная | Обязательно | По умолчанию | Описание |
|---|---|---|---|
| `BOT_TOKEN` | **да** | — | Токен от [@BotFather](https://t.me/BotFather). Без него бот печатает подсказку и выходит с кодом `1`. |
| `MODULES` | нет | `health` | Список включённых модулей через запятую. Неизвестное имя — понятная ошибка и выход `1`. |
| `LOG_LEVEL` | нет | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`. Неизвестное значение — откат к `INFO`. |
| `STORAGE_PATH` | нет | `data/botcore.db` | Файл SQLite для `SqliteStorage`. |

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

export BOT_TOKEN=123456:your-token
python -m core
```

Остановка — `Ctrl+C` или `SIGTERM`: бот перестаёт забирать новые апдейты и дожидается тех,
что уже в работе, затем закрывает хранилище и сессию Telegram.

Без токена:

```console
$ python -m core
BOT_TOKEN is not set, so the bot cannot start.
...
$ echo $?
1
```

## Проверки

```bash
ruff check .
ruff format --check .
mypy core          # strict
pytest -q
```

Те же три шага выполняет GitHub Actions (`.github/workflows/ci.yml`) на каждый push и pull request,
на Python 3.11 и 3.14.

## Как добавить модуль

1. Создайте `modules/<name>.py` с `MODULE_NAME` и фабрикой `create_router(context: ModuleContext) -> Router`.
2. Зарегистрируйте её в `modules/__init__.py` внутри `build_default_registry()`.
3. Включите модуль через `MODULES=health,<name>`.

Общие зависимости приходят в хендлеры через DI aiogram: `BotApp` кладёт хранилище в
`dispatcher["storage"]`, поэтому хендлер может объявить параметр `storage: StorageInterface`.

## Границы

- `StorageInterface` — это только `get` / `set` / `delete` / `close` по строковому ключу.
  Схем бизнес-сущностей в репозитории нет намеренно.
- `mypy --strict` проходит по `core/`; `modules/` и `tests/` типизированы, но не под strict.
