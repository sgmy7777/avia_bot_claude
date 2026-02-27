# Деплой на Railway — пошаговая инструкция

## Шаг 1. Залить код на GitHub

Если репозитория ещё нет:

1. Зайди на https://github.com/new
2. Создай репозиторий (например `avia_bot`), **приватный**
3. В папке проекта на Mac выполни:

```bash
cd /путь/до/avia_bot
git init
git add .
git commit -m "init"
git remote add origin https://github.com/ТОЙ_НИКНЕЙМ/avia_bot.git
git push -u origin main
```

---

## Шаг 2. Зарегистрироваться на Railway

1. Открой https://railway.app
2. Нажми **"Login"** → **"Login with GitHub"**
3. Авторизуй Railway доступ к репозиториям

---

## Шаг 3. Создать новый проект

1. На дашборде нажми **"New Project"**
2. Выбери **"Deploy from GitHub repo"**
3. Найди свой репозиторий `avia_bot` и нажми на него
4. Railway автоматически найдёт `Dockerfile` и начнёт сборку

---

## Шаг 4. Добавить PostgreSQL базу данных

1. В проекте нажми **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway создаст базу и добавит переменную `DATABASE_URL` автоматически
3. Убедись что в переменных окружения появился `DATABASE_URL` вида:
   `postgresql://postgres:...@...railway.app:5432/railway`

---

## Шаг 5. Добавить переменные окружения

1. Нажми на сервис `avia_bot` → вкладка **"Variables"**
2. Добавь каждую переменную через **"+ New Variable"**:

```
TELEGRAM_BOT_TOKEN        = токен от @BotFather
TELEGRAM_CHANNEL          = @avia_crash
TELEGRAM_ALERT_CHAT_ID    = (числовой ID или @username служебного чата, можно оставить пустым)

LLM_PROVIDER              = openrouter
OPENROUTER_API_KEY        = твой ключ OpenRouter
OPENROUTER_MODEL          = deepseek/deepseek-chat
OPENROUTER_BASE_URL       = https://openrouter.ai/api/v1
OPENROUTER_SITE_URL       = https://github.com/ТОЙ_НИКНЕЙМ/avia_bot
OPENROUTER_APP_NAME       = avia_bot

POLL_INTERVAL_MINUTES     = 10
MAX_PUBLICATIONS_PER_CYCLE = 3
DATE_WINDOW_DAYS          = 1
DRY_RUN                   = false
LOG_LEVEL                 = INFO
LOG_FORMAT_JSON           = true
USER_AGENT                = avia-bot/1.0 (+https://github.com/ТОЙ_НИКНЕЙМ/avia_bot)
```

> DATABASE_URL добавлять НЕ НУЖНО — Railway подставит его автоматически из PostgreSQL сервиса.

---

## Шаг 6. Проверить деплой

1. Перейди на вкладку **"Deployments"**
2. Дождись статуса **"Success"** (обычно 2-3 минуты)
3. Перейди на вкладку **"Logs"** — должны появиться строки вида:
   ```
   {"ts":"...","level":"INFO","msg":"starting worker | interval=10 min"}
   {"ts":"...","level":"INFO","msg":"fetched 100 candidate incidents"}
   ```

---

## Шаг 7. Настроить автодеплой

По умолчанию Railway автоматически деплоит при каждом `git push` в ветку `main`.
Это значит: поправил промпт → сделал push → Railway сам пересобрал и запустил бота.

---

## Лимиты бесплатного плана Railway

| Параметр | Значение |
|---|---|
| Кредиты в месяц | $5 |
| Примерная стоимость бота | ~$1-2/месяц |
| PostgreSQL | включён в кредиты |
| Лимит RAM | 512 MB (боту хватит) |

При превышении $5 Railway **остановит** сервис до следующего месяца.
Чтобы не превысить — держи `POLL_INTERVAL_MINUTES=10` и не ставь большие модели.

---

## Часто возникающие проблемы

### Бот запустился но ничего не публикует
Проверь логи на вкладке Logs. Скорее всего не задан `TELEGRAM_BOT_TOKEN` или бот не добавлен в канал.

### Ошибка `could not connect to server` в логах
Railway ещё не успел поднять PostgreSQL. Подожди 1-2 минуты и задеплой повторно.

### `psycopg2` не устанавливается
В `requirements.txt` должен быть именно `psycopg2-binary`, не `psycopg2`.

### Деплой завис на "Building"
Зайди в Deployments → нажми на деплой → посмотри Build Logs. Скорее всего ошибка в `Dockerfile`.

---

## Обновление кода

```bash
# После любых изменений:
git add .
git commit -m "update prompt"
git push

# Railway автоматически пересоберёт и перезапустит бота
```
