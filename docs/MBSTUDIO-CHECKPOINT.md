# MBStudio: установка и SEO — 16 сентября 2026

Этот чекпойнт сохраняет результат внедрения и точку продолжения для тиражирования SCENA. Основной адрес окончательно установлен: **https://mbstudio.scena.life**.

## Версии и доказательства

- [Репозиторий](https://github.com/moldset-mmc/scenaonline), production branch `main`.
- Версия приложения: [`6c1402ec0ccef9709ed67fd4e20f6d4fd8bd5c5c`](https://github.com/moldset-mmc/scenaonline/commit/6c1402ec0ccef9709ed67fd4e20f6d4fd8bd5c5c). GitHub `main` и чистая локальная рабочая копия сверены до подготовки данного пакета.
- Vercel project `scenaonline`, ID `prj_1uMoeCzIfiqptGDmFYYIteSpwqc6`.
- [Production deployment из итогового отчёта](https://vercel.com/moldset-8968s-projects/scenaonline/CaSGwvnrgzNA7KsFXX17mHxt3PLe): `dpl_CaSGwvnrgzNA7KsFXX17mHxt3PLe`, READY на момент проверки 16.09.2026.
- Этот пакет подготовлен для ветки `checkpoint/mbstudio-installation-2026-09-16`. Его коммит отличается от версии приложения; автодеплой этой ветки отключён точным правилом `vercel.json`. Факт публикации подтверждается чтением ветки GitHub после разрешённой отправки.

Внешние результаты ниже перенесены из сохранённого итогового отчёта `MBStudio-SEO-result.md` от 16.09.2026. Они не выдаются за новый опрос кабинетов поисковиков. При подготовке данного пакета попытка чтения `/healthz` через веб-инструмент не вернула проверяемого ответа; новый статус production этим действием не подтверждён и сбой сайта из этого не следует.

## Что было выполнено

| Область | Результат проверок 16.09.2026 |
| --- | --- |
| Адрес | HTTPS `mbstudio.scena.life`; сохранены существующие проект и данные |
| Runtime | Native HTML/Tornado; постоянная база Turso; Public/Private Blob |
| ЧПУ | RU/RO/EN; старые публичные GET/HEAD переводятся постоянным 308 |
| Sitemap | 27 канонических страниц; 12 пустых разделов исключены до появления материалов |
| Метаданные | У 27 страниц sitemap заполнены уникальные Title/Description |
| H1 | 39 проверенных публичных страниц имеют ровно один H1; у 27 страниц sitemap заголовки уникальны |
| Языки | Проверены HTML lang, canonical и взаимные hreflang; локализована география Кишинёва |
| Текст / разметка | Опубликованы описания реальных услуг; HTML доступен без обязательного JS; JSON-LD соответствует публикуемым сущностям |
| Google | Подтверждён `sc-domain:scena.life`, покрывающий поддомен; карта обработана: 27 адресов, 0 ошибок, 0 предупреждений |
| Яндекс | Права на точный HTTPS-хост подтверждены; sitemap принята в очередь |
| Метрика | Счётчик `112712591`; пять целей; отладчиком подтверждены PageView и `booking_open` |

Google GSC API, сохранённый результат:

```text
lastSubmitted=2026-09-16T12:02:37.896Z
lastDownloaded=2026-09-16T12:02:39.686Z
isPending=false
submitted=27
errors=0
warnings=0
```

URL Inspection главной `/ru/` тогда сообщил `URL is unknown to Google`. Это не противоречит обработке карты: индексация — отдельный этап.

Метрика: 16.09.2026 в 12:13:47 UTC официальный отладчик показал PageView для `/ru/zapis/` и Reach goal `booking_open`. Цели: `booking_open`, `booking_request`, `shop_order`, `course_request`, `contact_click`. Успешные формы проверялись на изолированных данных; реальные клиентские обращения для теста не создавались.

В итоговом отчёте записаны 353 unit-теста с 3 необязательными пропусками, 86 прежних SEO HTTP-проверок и 120 проверок новых маршрутов через два экземпляра; после уточнений H1/диагностики повторены соответствующие 12 и 19 тестов. Эти числа — квитанция предыдущего внедрения. Для нынешнего документального пакета проверяются ссылки, diff и конфигурация ветки; новая полная приёмка приложения не заявляется.

## Пределы результата

- Индексация всех URL, позиции, реальный поисковый трафик и заявки пока не подтверждены.
- [72 поисковые формулировки](MBSTUDIO-keywords.csv) — карта тем с `volume=not measured`, а не частотное ядро.
- Не измерены внешние совпадения текстов и цитирование ИИ-системами.
- В SEO-проходе использовался браузер; физическое устройство Samsung не проверялось.
- Нейтральный установщик второго владельца и автоматическая оплата ещё не подтверждены как готовые.
- Git не содержит актуальную базу и загруженные владельцем оригиналы. Этот checkpoint сохраняет код, схему и правила; для восстановления данных нужен приватный backup.

## Продолжение

В итоговом отчёте назначен контроль **21.09.2026, 11:30 Europe/Chisinau**. При подготовке данного пакета состояние расписания не перепроверялось; дубликат задачи не создавался.

1. Проверить доступность основного адреса и точную опубликованную версию.
2. Проверить Google sitemap и URL Inspection ключевых страниц.
3. Проверить обработку карты Яндексом. Повторная регистрация или отправка без выявленной причины не требуется.
4. Проверить накопление посещений/целей Метрики и отделить служебные проверки от реальных клиентов.
5. Зафиксировать подтверждённое, вывод и непроверенное. Новые правки предлагать по конкретной проблеме.

Отдельное направление, запрошенное владельцем после SEO-стопа: сохранить архитектуру и инструкции в GitHub для тиражирования и монетизации. Основа этого направления — [DEPLOYMENT.md](../DEPLOYMENT.md), [REPLICATION.md](REPLICATION.md), [SEO-STANDARD.md](SEO-STANDARD.md), [ADR-001](decisions/001-account-boundary.md).

Не повторять перенос MBStudio, создание его базы/хранилищ, регистрацию ресурсов или счётчика. Не удалять квитанции выполненных миграций и не перезаписывать поздние правки владельца.

## Resume instruction

Read this checkpoint, DEPLOYMENT.md, REPLICATION.md and SEO-STANDARD.md before continuing. Preserve the existing MBStudio origin and data. Treat deployment and integration receipts as dated evidence until checked in primary sources. The current code serves one owner per installation. A request to replicate accounts must first address the documented pilot-specific defaults and migrations; do not clone production customer data or claim an automated SaaS installer exists. Keep new-instance setup separate from updating/restoring an existing owner. Prepare exact changes, follow the owner's current approval rules, and report verified evidence in concise Russian.
