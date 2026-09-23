# SCENA

Личная Fashion & Beauty Сцена: знакомство, профессиональные услуги, Model и собственный Market. Интерфейс рассчитан прежде всего на смартфон и поддерживает русский, румынский и английский языки.

В репозитории находится исходный код **SCENA Pilot V1.7**, оформление и стартовые фотографии. Установленная база владельца, заявки, заказы, переписка, загруженные пользователем файлы и ключи подключений в Git не входят.

Состояние запуска и порядок продолжения на 14 сентября 2026 года: [SCENA_CURRENT.md](SCENA_CURRENT.md). Подключения базы и двух хранилищ: [HOSTING-PROPOSAL.md](deploy/HOSTING-PROPOSAL.md). Пароль кабинета, смена и восстановление доступа: [CABINET-ACCESS.md](CABINET-ACCESS.md).

## Запустить на компьютере

На Windows откройте **START-SCENA.cmd** в полной папке проекта. Программа подготовит окружение, попросит пароль и откроет сайт в браузере. Python 3.11 или новее должен быть установлен.

На macOS или Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start_scena.py
```

При первом запуске создаётся новая локальная база. Для переноса существующих данных используйте инструкцию в [LOCAL-GUIDE.md](LOCAL-GUIDE.md).

## Что входит

- **Моя Сцена** — личная история, фотографии, публикации и переходы к направлениям.
- **Professional** — услуги, портфолио, месячный календарь и заявки на запись.
- **Model** — знакомство, сменяющиеся образы, портфолио и приглашения в проекты.
- **Market** — товары с личной рекомендацией, корзина и заказы.
- **Рабочий кабинет** — редактирование страниц, расписание, продвижение, QR-коды и библиотека промптов.
- **PRO и помощь** — пробный доступ, подписанные коды продления, ассистент и обращения команде.

Подключение ответов нейросети и Telegram выполняется отдельными ключами владельца. Условия оплаты заказов согласовываются с покупателем; автоматического списания с карты нет.

## Размещение в интернете

Приложение работает на **Streamlit**. Локальная версия использует SQLite и файлы. Облачная сборка `Dockerfile.vercel` запускает постоянное хранение в Turso, оригиналы в Private Blob и опубликованные изображения в Public Blob. Вход в кабинет защищён серверным паролем и cookie с ограниченным сроком действия.

Постоянный адрес проекта: https://scenaonline.vercel.app ; кабинет: https://scenaonline.vercel.app/auth/login . Текущий статус публикации и проверки: [SCENA_CURRENT.md](SCENA_CURRENT.md). Подключения: [deploy/HOSTING-PROPOSAL.md](deploy/HOSTING-PROPOSAL.md). Пароль: [CABINET-ACCESS.md](CABINET-ACCESS.md).

Для облачной сборки используются зависимости `requirements-cloud.txt`; автономная установка сохраняет `requirements.txt`. Изолированный `deploy/start_preview.py` предназначен только для временных проб и не принимает реальные данные.

## Проверка кода

```sh
.venv/bin/python -m unittest discover -s tests
```

Проверки используют временные базы. Описание ранее проведённых проверок V1.7 — [VERIFICATION.md](VERIFICATION.md). Они подтверждают локальную версию; проверка онлайн-размещения выполняется отдельно.

## Инструкции

- [Работа, обновление и резервные копии](LOCAL-GUIDE.md)
- [AI и подключения](CONNECTIONS.md)
- [Telegram](TELEGRAM-SETUP.md)
- [Промпты](PROMPT-LIBRARY-GUIDE.md)
- [QR-визитки](QR-CAMPAIGNS.md)
- [Продление PRO](PRO-RENEWAL-SETUP.md)

Сведения о поставляемых шрифтах сохранены в [licenses/URW-Base35.txt](licenses/URW-Base35.txt).

### SCENA.LIVE card and questionnaire

The platform card is at `/newcard`. Its independent questionnaire backend and
`@scenalive_bot` setup are documented in [deploy/SCENA-INTAKE.md](deploy/SCENA-INTAKE.md).
Telegram intake stays disabled until dedicated database, private photo storage,
bot credentials and the owner's personal recipient are configured and verified.
