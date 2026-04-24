# Документация для разработчиков: pachka-bot

Бот публикует в Пачке агрегированные отчёты по портфелям Yandex Tracker: домен → поддомены → команды → проекты. Команда в чате (`/show_domain_report`, `/show_team_risk`, …) превращается в сетевые вызовы к Tracker и Markdown-ответ в Пачку.

---

## 1. Архитектура

```
Пачка (чат) ──webhook──▶ FastAPI (app/api/webhook.py)
                              │
                              ▼
                  CommandRouter (app/commands/router.py)
                              │
                              ▼
                  StatusAggregator (app/report/aggregator.py)
                              │
                              ▼
              YandexTrackerClient (app/tracker/client.py)
                              │
                              ▼
          Yandex Tracker API /v2/entities/portfolio|project
                              │
                              ▼
            Rendering (app/report/builder.py) ──▶ Markdown
                              │
                              ▼
                  PachcaClient (app/pachca/client.py)
                              │
                              ▼
                   Пачка API /messages
```

Сервис stateless по HTTP-запросам, состояние двухшагового диалога хранится в памяти процесса (`CommandRouter._pending`) и сбрасывается при рестарте — это допустимо.

### 1.1. Модули

| Модуль | Ответственность |
|---|---|
| `app/main.py` | Bootstrap FastAPI, lifespan, инициализация клиентов. |
| `app/config.py` | Pydantic-настройки из `.env`. |
| `app/api/webhook.py` | HTTP-эндпоинт `POST /webhook/pachca`, HMAC-проверка подписи, передача в router. |
| `app/api/health.py` | `GET /health` — пинг Tracker/Пачка. |
| `app/commands/router.py` | Парсинг slash-команд, двухшаговый диалог выбора портфеля. |
| `app/tracker/client.py` | HTTP-клиент Tracker (entities API: portfolio, project, comments). |
| `app/tracker/models.py` | Dataclasses `Portfolio`, `Project`, `Comment`, `TrackerUser`. |
| `app/status/mapping.py` | Маппинг Tracker `entityStatus` → `BusinessStatus`. |
| `app/status/parser.py` | Парсер `#WeeklyStatus` комментариев. |
| `app/report/aggregator.py` | Сборка `ProjectSummary` по дереву портфелей, дедупликация. |
| `app/report/builder.py` | Render Markdown для отчётов/списков/`help`. |
| `app/pachca/client.py` | Клиент Пачки: отправка сообщений. |
| `scripts/` | Отладочные выгрузки из Tracker (одноразовые). |
| `tests/` | pytest (unit, async). |

### 1.2. Стек

- Python 3.11+
- FastAPI + uvicorn
- httpx (async HTTP)
- pydantic / pydantic-settings
- structlog (JSON-логи в проде, console в DEBUG)
- pytest + pytest-asyncio
- Docker + docker-compose

---

## 2. Бизнес-логика

### 2.1. Дерево портфелей

В Tracker проекты организованы в трёхуровневое дерево портфелей:

```
Домен (top-level portfolio)
└── Поддомен
    └── Команда
        └── Проект (Project entity)
```

`PORTFOLIO_DOMAIN_IDS` задаёт список доменов верхнего уровня (через запятую). Бот не «угадывает» уровни — он ходит по `parentEntity` через `_search` с фильтром по родителю.

### 2.2. Источник статуса проекта

Для каждого проекта бизнес-статус вычисляется так (см. `StatusAggregator._summarize`):

1. Если `project.entity_status` не входит в `TRACKER_STATUS_MAP` (т.е. не `according_to_plan`, `at_risk`, `blocked`) → проект **пропускается полностью** (не попадает ни в один отчёт). Логируется событие `project.skipped`.
2. Запрашиваем все комментарии проекта через `GET /v2/entities/project/{id}/comments`.
3. Фильтруем — оставляем те, что содержат тег `#WeeklyStatus` (регистронезависимо).
4. Берём самый свежий такой комментарий как «последний статус».
5. Если комментария нет ИЛИ он старше `STATUS_FRESHNESS_DAYS` (по умолчанию 6 дней) → `is_stale = True`, бизнес-статус принудительно = `UNKNOWN`.
6. Иначе — берём `project.entity_status` и маппим через `TRACKER_STATUS_MAP`.

### 2.3. Маппинг статусов Tracker → бизнес-статус

Таблица из `app/status/mapping.py`:

| `entity_status` (API Tracker) | UI Tracker          | `BusinessStatus` | Эмодзи | Попадает в отчёт |
|-------------------------------|---------------------|------------------|--------|------------------|
| `according_to_plan`           | По плану            | `ON_TRACK`       | 🟢     | да               |
| `at_risk`                     | Есть риски          | `AT_RISK`        | 🟡     | да               |
| `blocked`                     | Заблокирован        | `BLOCKED`        | 🔴     | да               |
| любой другой (`draft`, `in_progress`, `launched`, `paused`, `null`) | — | — | — | **нет, проект скрыт** |

Проекты с нераспознаваемым `entity_status` отфильтровываются на уровне агрегатора (шаг 1 в §2.2) и не появляются ни в одном типе отчёта.

Среди оставшихся (с распознанным статусом): если комментарий просрочен или отсутствует → бизнес-статус принудительно `UNKNOWN` (⚪), проект в отчёте виден, но помечен как устаревший.

### 2.4. Формат комментария `#WeeklyStatus`

```
#WeeklyStatus
Comments: <произвольный текст, может быть многострочным>
DL по решению: <дедлайн в любом формате>
```

Поля case-insensitive, порядок не важен. Всё, что после `Comments:` до следующего помеченного блока, склеивается в `comments`. См. `app/status/parser.py`.

### 2.5. Дедупликация

Проект может быть прикреплён сразу к нескольким командам (если команды делят работу).

- **Отчёт по команде** — дедупликации нет: каждый проект команды показываем как есть.
- **Отчёт по поддомену** — обходим поддомен → команды → проекты, **dedup по `project.id`**.
- **Отчёт по домену** — обходим домен → поддомены → команды → проекты, **dedup по `project.id`**.

Комментарии проекта запрашиваются один раз на уникальный ID, чтобы не бить Tracker API лишними вызовами.

### 2.6. Поля проекта в отчёте

Запрос полей: `PROJECT_FIELDS = "summary,description,entityStatus,parentEntity,lead,start,end,tags"` (`app/tracker/client.py`).

| Поле в отчёте | Tracker API path | Модель | Примечание |
|---|---|---|---|
| Название проекта | `fields.summary` | `Project.summary` | Используется как текст гиперссылки. |
| Ответственный | `fields.lead.display` | `Project.lead.display` | Если `null` или `lead` не назначен → показывается `—`. |
| Заказчик | `fields.clients[].display` | `Project.clients` | Массив пользователей; отображается через запятую. Строка скрыта, если список пуст. |
| Статус (эмодзи) | `fields.entityStatus` | `Project.entity_status` | Маппинг см. §2.3; итоговый статус — только при свежем `#WeeklyStatus`. |
| Дедлайн | `fields.end` | `Project.end` | Строка `YYYY-MM-DD` как возвращает Tracker; не отображается если `null`. |
| Комментарий/DL | комментарии проекта | `Comment.body` → `WeeklyStatus` | Парсится из `#WeeklyStatus`-комментариев, §2.2. |

URL проекта строится из `short_id` (числовой идентификатор) по шаблону `{TRACKER_WEB_BASE}/pages/projects/{short_id}`, аналогично для портфелей — `{TRACKER_WEB_BASE}/pages/portfolios/{id}/projects`.

### 2.7. Фильтры отчётов

`render_report` показывает все проекты, прошедшие фильтр агрегатора (т.е. `ON_TRACK`, `AT_RISK`, `BLOCKED`, а также `UNKNOWN` для тех, у кого распознаваемый статус, но устаревший комментарий). Фильтрация по бизнес-статусу — в `builder.py`:

- `render_risk` → только `AT_RISK` (заблокированные **не** включаются).
- `render_blocked` → только `BLOCKED`.
- `render_on_track` → только `ON_TRACK`.
- `render_cross` → только проекты, у которых в `Project.tags` есть значение `"cross"` (регистронезависимо).

Пустые результаты рендерятся отдельным сообщением (`Проектов с рисками нет.` и т.п.).

### 2.8. Отличие «устарело» от «не заполнено»

- Комментария нет вообще → `Статус не заполнен (добавьте комментарий с #WeeklyStatus).`
- Комментарий есть, но старше 6 дней → `Данные устарели (старше 6 дней).` + показываем старый текст как reference.

### 2.9. Диалог выбора портфеля

Выбор всегда начинается с домена и при необходимости углубляется:

| Команда | Шаги диалога |
|---|---|
| `/show_domain_*` | домен |
| `/show_subdomain_*` | домен → поддомен |
| `/show_team_*` | домен → команда (все команды внутри выбранного домена, плоский список) |

Любой шаг с единственным вариантом пропускается. Состояние хранится в `CommandRouter._pending: dict[chat_id, _PendingSelection]` и содержит `current_level` (что сейчас выбираем) и `final_level` (до чего нужно дойти). После выбора домена, если `current_level != final_level`, `_ask_within_domain` вычисляет дочерние портфели и продолжает диалог уже внутри домена.

---

## 3. API контракт

### 3.1. HTTP эндпоинты бота

| Метод | Путь               | Назначение                                   |
|-------|--------------------|----------------------------------------------|
| POST  | `/webhook/pachca`  | Вебхук Пачки с командами пользователей.      |
| GET   | `/health`          | Состояние: `tracker` + `pachca` ping.        |

### 3.2. Проверка подписи вебхука

Пачка подписывает тело запроса:

```
X-Pachca-Signature: sha256=<hex-hmac-sha256(body, WEBHOOK_API_KEY)>
```

Реализация: `app/api/webhook.py::_verify_signature`. При неверной подписи — `warning`-лог, но (по текущей конфигурации) запрос всё ещё обрабатывается. Для prod-режима имеет смысл сделать запрос жёстко отклоняемым (см. §5 TODO).

### 3.3. Slash-команды

16 команд (см. подробно `Docs/user-guide.md`):

- `/help`
- `/show_{domain,subdomain,team}_list`
- `/show_{domain,subdomain,team}_{report,risk,blocked,on_track}`
- `/show_cross_{domain,subdomain,team}`

Неизвестная команда → `Неизвестная команда. Введите /help для справки.`

### 3.4. Используемые endpoint'ы Tracker

- `GET /v2/myself` — проверка OAuth-токена (health).
- `GET /v2/entities/portfolio/{id}` — один портфель.
- `POST /v2/entities/portfolio/_search` — дети портфеля (фильтр `parentEntity`).
- `GET /v2/entities/project/{id}` — один проект.
- `POST /v2/entities/project/_search` — проекты в портфеле.
- `GET /v2/entities/project/{id}/comments` — комментарии проекта.

Заголовок организации: `X-Org-ID` для Yandex 360 / `X-Cloud-Org-ID` для Yandex Cloud Org (управляется `TRACKER_ORG_TYPE`).

### 3.5. Используемые endpoint'ы Пачки

- `GET /users/me` — ping.
- `POST /messages` — отправка сообщения (`entity_type: "discussion"`, `entity_id: chat_id`).

Сообщения >4000 символов режутся на блоки по пустым строкам (`PachcaClient._split`).

---

## 4. Конфигурация (`.env`)

Переменные из `app/config.py`:

| Переменная | Обязательная | По умолчанию | Описание |
|---|---|---|---|
| `TRACKER_OAUTH_TOKEN` | да | — | OAuth-токен Tracker. |
| `TRACKER_ORG_ID` | да | — | Идентификатор организации. |
| `TRACKER_API_BASE` | нет | `https://api.tracker.yandex.net` | Базовый URL API. |
| `TRACKER_WEB_BASE` | нет | `https://tracker.yandex.ru` | Для сборки ссылок на проекты/портфели. |
| `TRACKER_ORG_TYPE` | нет | `360` | `360` или `cloud`. |
| `PORTFOLIO_DOMAIN_IDS` | да | — | Список ID доменов через запятую. |
| `PACHCA_ACCESS_TOKEN` | да | — | Bearer-токен бота в Пачке. |
| `PACHCA_API_BASE` | нет | `https://api.pachca.com/api/shared/v1` | |
| `PACHCA_TARGET_CHAT_ID` | да | — | Нужен для проверок/утилит (бот отвечает в тот же чат, откуда пришёл вебхук). |
| `WEBHOOK_API_KEY` | да | — | Shared secret для HMAC-подписи вебхука. |
| `APP_HOST` | нет | `0.0.0.0` | |
| `APP_PORT` | нет | `8080` | |
| `LOG_LEVEL` | нет | `INFO` | `DEBUG` включает human-readable console-рендер. |
| `STATUS_FRESHNESS_DAYS` | нет | `6` | Порог устаревания `#WeeklyStatus`. |
| `WEEKLY_STATUS_TAG` | нет | `#WeeklyStatus` | Тег для распознавания статуса. |

Шаблон — `.env.example` в корне.

---

## 5. Локальная разработка

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env           # заполнить секреты
uvicorn app.main:app --reload
pytest                          # 77 тестов, async
ruff check .                    # линтер
mypy app                        # типы
```

Структура тестов:

- `tests/test_tracker_client.py` — проверка парсинга ответов Tracker (через `pytest-httpx`).
- `tests/test_aggregator.py` — бизнес-логика дедупа/свежести.
- `tests/test_command_router.py` — двухшаговый диалог, multi-domain.
- `tests/test_report_builder.py` — рендер Markdown.
- `tests/test_status_parser.py` / `tests/test_status_mapping.py` — парсер и маппинг.
- `tests/test_pachca_client.py` — клиент Пачки, разбиение длинных сообщений.
- `tests/test_webhook.py` — HMAC, integration через FastAPI TestClient.

---

## 6. Развёртывание в контуре компании

Сейчас (MVP) сервис развёрнут в личном контуре Максима Дегтярёва: VPS Yandex Cloud, Docker. При переходе в продуктивный контур компании нужно:

### 6.1. Переносимые артефакты

1. Репозиторий (текущая ветка `main`).
2. Образ: `docker build -t registry.company.example/pachka-bot:<version> .` — пушить в корпоративный registry.
3. `.env.example` как шаблон секретов (сами значения — через секрет-хранилище, см. §6.4).

### 6.2. Инфраструктура (минимум)

| Ресурс | Требование |
|---|---|
| Compute | 1 vCPU, 512 MB RAM достаточно (сервис однопроцессный, нагрузка — десятки вебхуков в сутки). |
| Диск | 5 GB (только образ + логи). |
| Сеть | Входящий HTTPS 443 извне (для Пачки). Исходящий HTTPS к `api.tracker.yandex.net` и `api.pachca.com`. |
| DNS | Домен компании, напр. `pachka-bot.company.example`. |
| TLS | Сертификат компании (внутренний CA или публичный). Пачка требует HTTPS. |
| Reverse proxy | nginx / Traefik / корпоративный ingress — терминирует TLS, проксирует на `:8080`. |

### 6.3. Варианты развёртывания

**A. Kubernetes (рекомендуется для долгой эксплуатации).** Написать `Deployment` + `Service` + `Ingress`. Секреты — `Secret`/`ExternalSecrets`. Health-probe — `GET /health`.

**B. Docker Compose на VM.** Быстрее развернуть, достаточно для текущей нагрузки. Шаги:

```bash
# на хосте
git clone <repo> /opt/pachka-bot
cd /opt/pachka-bot
sudo vim .env              # секреты
sudo docker compose up -d
sudo docker compose logs -f bot
```

Reverse proxy (пример `nginx`):

```
server {
    listen 443 ssl;
    server_name pachka-bot.company.example;
    ssl_certificate     /etc/ssl/company/fullchain.pem;
    ssl_certificate_key /etc/ssl/company/privkey.pem;

    location /webhook/pachca { proxy_pass http://127.0.0.1:8080; }
    location /health         { proxy_pass http://127.0.0.1:8080; }
}
```

### 6.4. Секреты

Не хранить в репозитории. В зависимости от контура:

- Kubernetes → `Secret` + `ExternalSecrets`/`Vault Agent Injector`.
- Docker Compose → `.env` с правами `600`, владелец — сервисный пользователь.
- Yandex Cloud Lockbox / HashiCorp Vault — предпочтительно для ротации.

Что нужно завести:

1. Сервисный аккаунт в Tracker → OAuth-токен (`TRACKER_OAUTH_TOKEN`). У аккаунта должен быть доступ на чтение к целевым доменам/поддоменам/командам/проектам.
2. Бот в Пачке → `PACHCA_ACCESS_TOKEN`, `WEBHOOK_API_KEY` (общий секрет для подписи).
3. `TRACKER_ORG_ID`, `PORTFOLIO_DOMAIN_IDS` — получить от владельцев портфелей компании.

### 6.5. Настройка интеграции

1. **Пачка → Настройки чат-бота**:
   - URL вебхука: `https://pachka-bot.company.example/webhook/pachca`
   - Секрет подписи: тот же, что `WEBHOOK_API_KEY`.
   - Поле «Команды» — **оставить пустым** (иначе Пачка будет фильтровать события по списку и, например, `/help` может не прилетать).
   - Чекбокс «Игнорировать свои сообщения» — **включить** (иначе бот будет реагировать на собственные ответы и словит рекурсию).
2. **Tracker**: сервисный аккаунт → Администрирование → OAuth → выпустить токен с правом чтения entities.
3. Добавить бота в целевые чаты (домен/поддомен/команда).

### 6.6. Мониторинг и эксплуатация

- `/health` → healthcheck в Docker/Kubernetes, интервал 30s.
- Логи — JSON через structlog. Централизовать (ELK/Loki) по `req_id`, `chat_id`, `project_id`.
- Ключевые события: `webhook.received`, `webhook.done`, `project.status`, `webhook.auth_failed`, `command.failed`.
- Алерты:
  - `/health != healthy` более 5 минут.
  - Всплеск `webhook.auth_failed` (потенциально — утечка/ротация секрета).
  - `command.failed` > N/мин.

### 6.7. Чеклист миграции из персонального контура Максима

- [ ] Получить доступ к репозиторию и CI в корпоративном GitLab/GitHub.
- [ ] Выпустить корпоративный сервисный аккаунт в Tracker и пересоздать OAuth-токен.
- [ ] Создать/перевести бота в Пачке на корпоративный аккаунт и обновить токены.
- [ ] Зарегистрировать корпоративный домен + TLS.
- [ ] Развернуть сервис (Kubernetes/VM) и передать URL в настройки вебхука Пачки.
- [ ] Актуализировать `PORTFOLIO_DOMAIN_IDS` — список реальных доменов компании, которые бот должен обслуживать.
- [ ] Включить централизованное логирование и метрики.
- [ ] Положить secret-rotation в регламент (раз в 90 дней).
- [ ] После миграции — остановить старый сервис в личном контуре и отозвать его токены.

---

## 7. Расширение

### 7.1. Добавить новый уровень команды (например, `_summary`)

1. Добавить строку в `_ACTION_LABEL` (`app/commands/router.py`) и рендерер в `_RENDERERS`.
2. Написать `render_summary(...)` в `app/report/builder.py`.
3. Обновить `HELP_TEXT`.
4. Добавить тесты в `test_command_router.py` и `test_report_builder.py`.

### 7.2. Поддержать новый статус Tracker

Добавить ключ в `TRACKER_STATUS_MAP` (`app/status/mapping.py`) и, если нужно, новую константу в `BusinessStatus` + эмодзи/лейбл. Unit-тест в `test_status_mapping.py`.

### 7.3. Сменить источник статуса с комментариев на поле проекта

Достаточно переписать `StatusAggregator._summarize` — остальные слои уже работают с `ProjectSummary`.

---

## 8. Известные ограничения

- In-memory состояние `CommandRouter._pending` → при рестарте пользователь потеряет незавершённый диалог. Для текущей нагрузки приемлемо.
- Подпись вебхука проверяется, но обработка продолжается даже при несовпадении (остался `warning`-лог). Перед выкаткой в prod — ужесточить до отказа 401.
- Tracker rate limits: обходим всё дерево последовательно. При больших доменах (>500 проектов) может быть медленно; поставить семафор для параллелизации комментариев, если станет узким местом.
- Нет кэша: каждый вызов команды ходит в Tracker заново. Для часто запрашиваемых отчётов можно добавить TTL-кэш 30–60 с.
