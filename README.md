# pachka-bot

Бот для построения отчётностей из Yandex Tracker в мессенджер Пачка.

План внедрения: [`docs/implementation-plan.md`](docs/implementation-plan.md).

## Стек

- Python 3.11+
- FastAPI + uvicorn
- httpx (async)
- pydantic / pydantic-settings
- structlog
- pytest

## Быстрый старт (локально)

```bash
# 1. Установить зависимости
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Сконфигурировать окружение
cp .env.example .env
# заполнить TRACKER_OAUTH_TOKEN, PACHCA_ACCESS_TOKEN, WEBHOOK_API_KEY

# 3. Запустить
uvicorn app.main:app --reload

# 4. Прогнать тесты
pytest
```

## Структура

```
app/
├── api/         FastAPI роутеры (webhook, health)
├── commands/    Маршрутизация slash-команд Пачки
├── tracker/     Клиент Yandex Tracker + модели
├── pachca/      Клиент Пачки
├── status/      Парсер #WeeklyStatus и маппинг статусов
├── report/      Построение агрегированных отчётов
├── config.py    Настройки
└── main.py      FastAPI приложение

scripts/
└── dump_portfolios.py   Выгрузка дерева портфелей для проверки API

tests/          pytest
docs/           Документация (план внедрения)
```

## Эталонные портфели для MVP

| Уровень | ID |
|---|---|
| Домен | `69e213652577131acba63864` |
| Поддомен | `69e21375562b1c65ac0cdb8b` |
| Команда | `69e2138070fcad39d9d16d5f` |

## Безопасность

Секреты хранятся в `.env` (не коммитится). Для прода использовать хранилище секретов K8s / Vault.
