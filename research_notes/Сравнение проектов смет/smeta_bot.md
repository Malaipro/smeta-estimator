# Технический аудит leontov/smeta_bot

## Что проект фактически делает и какой пользовательский сценарий реализован

### Takeaway
Репозиторий — не готовый «промышленный» продукт, а одноразово опубликованный ранний каркас Telegram-бота и FastAPI API. Причём основной сценарий создания сметы фактически не подключён к запущенному боту: зарегистрирован только общий echo-обработчик.

### Cited Findings
- README заявляет мастер создания смет, Gemini, редактирование, историю, шаблоны, PDF/DOCX, роли, CRM/Google Sheets/email/webhooks, веб-панель и мониторинг — [README](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/README.md#L59-L72).
- Реально `register_handlers()` создаёт только один обработчик, отвечающий на любое сообщение «Бот работает! Скоро здесь будет мастер создания смет», и не подключает роутеры `smeta.py` и `history.py` — [регистрация обработчиков](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/__init__.py#L1-L8).
- Неподключённый сценарий в `smeta.py` запрашивает название и свободный текст, передаёт его Gemini, затем предлагает только PDF или DOCX — [FSM сметы](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L10-L33).
- При «сохранении» бот создаёт запись сметы с `total=0`, не разбирает и не сохраняет позиции, а в коде прямо оставлена пометка о будущем парсинге — [сохранение сметы](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L35-L60).
- Команда истории выводит только заголовки; `/get_smeta` не отдаёт документ, а сообщает, что экспорт ещё «реализуется» — [история](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/history.py#L8-L38).
- Отдельная минимальная доменная модель умеет только считать `quantity * price` по строкам и общую сумму; налоги, наценки, скидки, разделы, округление, валюты и версии отсутствуют — [модель расчёта](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/smeta/estimate.py#L1-L29).
- FastAPI содержит CRUD-каркасы для пользователей, смет, ролей, справочников, шаблонов, истории, интеграций и документов — [подключение роутеров](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/main.py#L2-L36).

### Inferences
- Для задачи друга проект нельзя использовать «как есть»: видимый пользователю бот не доходит до логики сметы, а расчёт через LLM возвращает неструктурированный текст без проверяемой арифметики и справочника цен — вывод из [регистрации обработчиков](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/__init__.py#L1-L8) и [Gemini-сценария](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L26-L33).
- Полезная часть репозитория — лишь идея структуры и простейшие SQLAlchemy-модели; бизнес-логику корректной строительной сметы потребуется проектировать заново — основание: [модели данных](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L10-L35) и [минимальная формула](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/smeta/estimate.py#L5-L29).

### Gaps
- В репозитории нет описания целевого вида строительной сметы, шаблона итогового документа, правил ценообразования или примера корректного результата, поэтому соответствие реальному процессу друга установить невозможно.
- Нет работающего публичного демо или опубликованного результата end-to-end проверки.

## Стек, архитектура, данные и внешние сервисы

### Takeaway
Стек — Python 3.11, aiogram, FastAPI, SQLAlchemy, Gemini, SQLite/PostgreSQL и заготовки S3/MinIO. Архитектура монолитная и синхронная; заявления о микросервисах, Kubernetes, очередях и веб-панели исходниками не подтверждаются.

### Cited Findings
- `pyproject.toml` объявляет Python 3.11+, aiogram 3, `google-generativeai`, SQLAlchemy, Alembic, FastAPI/Uvicorn, asyncpg/aiosqlite, python-docx и ReportLab — [pyproject.toml](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/pyproject.toml#L1-L27).
- Таблицы охватывают пользователей, сметы и строки, роли, справочники работ/материалов, шаблоны, историю, интеграции и документы — [SQLAlchemy-модели](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L10-L113).
- Gemini-интеграция состоит из вызова `gemini-2.5-flash`; файл не вызывает `genai.configure()` и не передаёт API-ключ модели — [Gemini-интеграция](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/integrations/gemini.py#L1-L11).
- Конфигурация перечисляет ключи OpenAI, speech/ElevenLabs, CRM, Google Sheets, email, S3/MinIO, Redis, Sentry/Grafana/ELK, но в исходниках реализованы лишь Gemini и S3/MinIO-клиенты — [конфигурация](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/config.py#L1-L48); [хранилище](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/integrations/storage.py#L1-L53).
- Документация обещает микросервисы, Kubernetes и Helm, но соответствующих манифестов в репозитории нет; сам документ состоит из четырёх строк деклараций — [architecture.md](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/docs/architecture.md#L1-L5).
- Docker Compose содержит только бота и PostgreSQL; API, воркеры, Redis и объектное хранилище в нём отсутствуют — [docker-compose.yml](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/docker-compose.yml#L1-L23).

### Inferences
- Это монолитный прототип, а не микросервисная система: бот напрямую выполняет синхронный вызов Gemini внутри async-обработчика и напрямую пишет в БД — [обработчик](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L26-L60).
- Значительная часть «интеграций» существует только в виде названий переменных окружения и типа строки в БД; оценивать их как готовые функции нельзя — [конфигурация](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/config.py#L10-L40) и [Integration](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L93-L101).

### Gaps
- Нет диаграммы реального потока данных, SLA, оценки нагрузки или доказательства работы с PostgreSQL.
- Не определено, какой именно внешний сервис должен быть обязательным в минимальном варианте.

## Excel и другие форматы выгрузки

### Takeaway
Excel-выгрузки и Excel-импорта в проекте нет вообще. Реализованы лишь крайне простые PDF/DOCX-файлы; даже заявленная интеграция с Google Sheets отсутствует как код.

### Cited Findings
- В зависимостях нет `openpyxl`, `xlsxwriter`, `pandas` или другой библиотеки XLSX — [pyproject.toml](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/pyproject.toml#L8-L27).
- Полный исходный код репозитория на коммите не содержит упоминаний `xlsx`, `openpyxl`, `xlsxwriter` или `excel`; дерево файлов также не содержит Excel-модуля — [дерево репозитория](https://github.com/leontov/smeta_bot/tree/d18fef146320de48a3d77124b2f65cda02ef9bfb).
- Google Sheets представлен только переменной `GOOGLE_SHEETS_CREDENTIALS` и комментарием о допустимом типе интеграции; клиентских вызовов Sheets нет — [конфигурация](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/config.py#L10-L19); [модель Integration](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L93-L101).
- DOCX создаётся одним абзацем, а PDF рисует каждую строку по фиксированным координатам без таблицы, переноса строк и пагинации — [генерация документов](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/utils/doc_gen.py#L1-L21).

### Inferences
- Для требуемой задачи XLSX-модуль придётся написать с нуля: определить колонки и разделы, формулы, стили, объединения, итоги, НДС/скидки, печатную область, ширины, русские числовые форматы, защиту формул и правила импорта/обратного редактирования.
- Текущий неструктурированный ответ Gemini нельзя надёжно выгрузить по ячейкам: сначала нужен детерминированный объект сметы и валидация каждой позиции — основание: [ответ Gemini сохраняется как текст](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L26-L32) и [позиции не парсятся](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L50-L54).

### Gaps
- Не предоставлен Excel-образец друга, поэтому нельзя определить, нужен ли только экспорт, двусторонний импорт, формулы, локальные сметные нормы или просто коммерческое предложение.

## Запуск и развёртывание

### Takeaway
Инструкция запуска противоречит репозиторию, а стандартный Docker Compose должен сломаться ещё до запуска приложения. Сборку и конфигурацию нужно исправлять до любой продуктовой доработки.

### Cited Findings
- README предлагает `pip install -r requirements.txt`, но `requirements.txt` отсутствует; есть только `pyproject.toml` без lock-файла — [быстрый старт](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/README.md#L5-L31); [дерево репозитория](https://github.com/leontov/smeta_bot/tree/d18fef146320de48a3d77124b2f65cda02ef9bfb).
- Compose задаёт `build: .`, что по умолчанию ожидает `Dockerfile` в корне контекста, но единственный Dockerfile лежит в `docker/Dockerfile`, а параметр `dockerfile:` не задан — [Compose](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/docker-compose.yml#L1-L11); [Dockerfile](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/docker/Dockerfile#L1-L6).
- `pyproject.toml` не объявляет импортируемые пакеты `pydantic-settings`, `python-jose`, `passlib`, `boto3`, `minio`, `python-multipart` и `email-validator`, поэтому чистая установка заявленных зависимостей не обеспечивает импорт API — [зависимости](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/pyproject.toml#L8-L27); [импорты config/auth/storage](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/config.py#L1-L3); [auth.py](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/auth.py#L1-L10); [storage.py](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/integrations/storage.py#L1-L4).
- PostgreSQL запускается в Compose, но показанная конфигурация приложения по умолчанию использует локальный SQLite, а пример PostgreSQL требует `psycopg2`, которого нет в зависимостях — [настройка БД](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/config.py#L6-L10); [.env.example](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/.env.example#L1-L8); [Compose PostgreSQL](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/docker-compose.yml#L12-L21).
- Alembic указан как зависимость и README обещает миграции, но в репозитории нет `alembic.ini` и каталога миграций; таблицы создаются через `Base.metadata.create_all()` — [pyproject.toml](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/pyproject.toml#L8-L18); [создание таблиц](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L37-L39).

### Inferences
- Минимальный путь запуска требует сначала исправить упаковку зависимостей, Docker-контекст, выбор БД, инициализацию Gemini, регистрацию роутеров и миграции; простой `docker-compose up --build` недостаточен.
- Для одного друга разумнее убрать неиспользуемые API/роли/S3/мониторинг, оставить один процесс Telegram или небольшой web-интерфейс, SQLite с резервным копированием и XLSX-экспорт; это снизит площадь отказа по сравнению с ремонтом всех заявленных сервисов.

### Gaps
- История Actions недоступна без отдельного просмотра результатов CI; сам workflow не доказывает, что тесты когда-либо прошли.
- Нет зафиксированного lock-файла, поэтому воспроизводимый набор фактических версий зависимостей неизвестен.

## Безопасность и целостность данных

### Takeaway
Публично разворачивать проект опасно: секреты находятся в Git, авторизация не подключена к рабочим API, есть ошибки модели пользователя и отсутствует разграничение доступа к сметам и документам.

### Cited Findings
- Репозиторий отслеживает `.env`, а не только `.env.example`; локальная read-only проверка коммита показала значения, синтаксически похожие на действующие Telegram- и Gemini-ключи. Значения здесь намеренно не приводятся — [.env в коммите](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/.env).
- При пустом `SECRET_KEY` код использует общую строку `supersecretkey` — [JWT-конфигурация](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/auth.py#L12-L17).
- Регистрация создаёт пользователя с `hashed_password`, но SQLAlchemy-модель `User` такого столбца не определяет, поэтому поток регистрации несовместим с моделью — [регистрация](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/auth.py#L35-L45); [User](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L10-L15).
- Ни один CRUD-роутер не использует `get_current_user` или `require_role`; функция проверки роли объявлена только внутри auth-модуля — [auth dependency](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/auth.py#L55-L82); [пример открытых estimates endpoints](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/estimates.py#L8-L43).
- API создания сметы жёстко присваивает `user_id=1`, а чтение возвращает все сметы без фильтра владельца — [estimates.py](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/estimates.py#L10-L40).
- Документы можно загружать от произвольного `user_id`, перечислять все, скачивать и удалять по ID без проверки пользователя — [documents.py](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/documents.py#L13-L66).
- Telegram `/get_smeta <id>` ищет смету только по ID, не проверяя владельца — [history.py](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/history.py#L27-L38).
- Имя выходного файла строится из пользовательского заголовка почти без очистки, что допускает проблемные разделители пути и коллизии имён — [формирование filename](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L35-L39); [запись на диск](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/utils/doc_gen.py#L6-L20).

### Inferences
- Потенциально действующие ключи из `.env` нужно считать скомпрометированными и отозвать/перевыпустить до любого форка; удаление файла новым коммитом не удалит его из истории — основание: [.env в неизменяемом коммите](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/.env).
- API нельзя выставлять в интернет без полной ревизии аутентификации, владения объектами, валидации загрузок, обработки имён файлов и секретов.
- Для личного однопользовательского прототипа безопаснее вообще не поднимать публичный REST API, пока он не нужен.

### Gaps
- Ключи намеренно не проверялись обращением к внешним сервисам, поэтому неизвестно, действуют ли они сейчас.
- В репозитории нет threat model, политики резервного копирования, удаления персональных данных и журналирования доступа.

## Качество кода, тесты, лицензия и зрелость

### Takeaway
Зрелость очень низкая: один коммит, нет релизов и версий, тесты узкие, а CI не делает заявленные линтинг, coverage, Docker-сборку или деплой. MIT позволяет переиспользовать код, но технически это скорее учебный/AI-сгенерированный каркас.

### Cited Findings
- На 1 ноября 2026 года в репозитории один коммит `d18fef1` от 9 июля 2025 года с сообщением `Initial commit`; GitHub показывает 0 звёзд и 2 форка — [репозиторий](https://github.com/leontov/smeta_bot); [фиксированный коммит](https://github.com/leontov/smeta_bot/commit/d18fef146320de48a3d77124b2f65cda02ef9bfb).
- `pyproject.toml` всё ещё содержит автора-заглушку `Your Name <your@email.com>` — [метаданные проекта](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/pyproject.toml#L1-L7).
- В репозитории восемь тестовых функций: health, простой арифметический total, CRUD справочников/шаблонов/истории/интеграций и документное хранилище с mock; нет тестов Telegram FSM, Gemini, auth/RBAC, estimates API, Excel, Docker или миграций — [tests](https://github.com/leontov/smeta_bot/tree/d18fef146320de48a3d77124b2f65cda02ef9bfb/tests).
- CI только устанавливает Poetry, выполняет `poetry install` и `pytest`; заявленных README линтинга, coverage, Docker и автосборки/деплоя в workflow нет — [ci.yml](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/.github/workflows/ci.yml#L1-L23); [заявление README](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/README.md#L71-L72).
- Схема ответа сметы ожидает поля `name` и `description`, а ORM-модель хранит `title` и не имеет `description`, что делает API-контракт несовместимым с моделью — [Pydantic EstimateRead](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/api/schemas/base.py#L149-L162); [ORM Estimate](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/db/models.py#L17-L35).
- Проект опубликован под MIT: разрешены использование, изменение и распространение при сохранении уведомления об авторских правах и текста лицензии — [LICENSE](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/LICENSE#L1-L23).

### Inferences
- Совокупность одного массового коммита, автора-заглушки, декларативных документов на 3–5 строк, неподключённых обработчиков и несовместимых моделей указывает на сгенерированный каркас без полного ручного end-to-end прохода; это вывод, а не подтверждённое автором происхождение — [commit](https://github.com/leontov/smeta_bot/commit/d18fef146320de48a3d77124b2f65cda02ef9bfb), [документация](https://github.com/leontov/smeta_bot/tree/d18fef146320de48a3d77124b2f65cda02ef9bfb/docs).
- Поддерживать этот код как основу продукта рискованнее, чем взять отдельные идеи моделей и собрать узкий проверяемый MVP.

### Gaps
- Нет issues, changelog, roadmap, релизов, опубликованного package/container image или подтверждённой пользовательской базы.
- Нельзя подтвердить статус CI только по наличию workflow; для итогового решения следует считать тесты непроверенными до чистой локальной/контейнерной сборки после исправления зависимостей.

## Реалистичная сложность внедрения

### Takeaway
Для задачи «друг считает сметы и выгружает Excel» ремонт всех обещанных возможностей невыгоден. Рациональный путь — выделить доменную модель и заново собрать небольшой MVP; текущий репозиторий может быть только справочным наброском.

### Cited Findings
- Базовая формула строки уже есть, но не связана с подключённым Telegram-сценарием и не имеет XLSX-экспорта — [формула](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/core/smeta/estimate.py#L5-L29); [реальный handler registry](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/__init__.py#L1-L8).
- До полезного сценария необходимо исправить минимум зависимости/сборку, регистрацию FSM, структурированное хранение позиций и экспорт — [pyproject](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/pyproject.toml#L8-L27); [сохранение только заголовка и нулевой суммы](https://github.com/leontov/smeta_bot/blob/d18fef146320de48a3d77124b2f65cda02ef9bfb/smetabot/bot/handlers/smeta.py#L35-L60).

### Inferences
- Оценка опытного Python-разработчика при наличии согласованного Excel-шаблона: **2–4 рабочих дня** только на восстановление запуска текущего каркаса и базового Telegram-потока, без качественной Excel-сметы и production-защиты.
- Для полезного однопользовательского MVP друга — ввод/редактирование строк, справочник цен, корректный подсчёт, SQLite, готовый `.xlsx`, простые резервные копии и тесты критических формул — ориентир **7–15 рабочих дней**. Быстрее и надёжнее собрать этот узкий контур отдельно, чем чинить все заявленные модули.
- Для многопользовательского production-варианта с web/Telegram, PostgreSQL-миграциями, RBAC, объектным хранилищем, аудитом, мониторингом, резервным копированием и полноценным тестированием — ориентир **6–12 недель** одного сильного разработчика после прояснения бизнес-правил.
- Если Excel — единственная обязательная выгрузка, Gemini лучше сделать необязательным помощником распознавания черновика, а арифметику и формирование XLSX оставить детерминированному коду.

### Gaps
- Сроки существенно зависят от образца Excel, перечня формул, режима использования (только друг или клиенты), необходимости Telegram/web и источника цен; без этих требований это диапазоны, а не календарная смета.
- Неизвестно, требуется ли соответствие нормативным сметным базам/ГЭСН/ФЕР/ТЕР; при таком требовании объём и юридические вопросы вырастут кратно.
