# SCENA — четыре приглашения

Каждое направление имеет самостоятельную фотографию и свой адрес. Исходные фотографии для лица Марии извлечены из предоставленных пользователем PDF «Мастер-Визажист.pdf», «model (2).pdf» и «model.pdf»; для профессионального образа также использован «Мастер-Визажист (2).pdf». Пять ранее утверждённых подиумных кадров не изменялись.

| Направление | Фотография | Маршрут |
|---|---|---|
| Моя Сцена | `media/qr-scenes/scene.png` | `?page=scene` |
| Professional | `media/qr-scenes/professional.png` | `?page=professional` |
| Model | `media/qr-scenes/model.png` | `?page=model` |
| Запись к мастеру | `media/qr-scenes/booking.png` | `?page=booking` |

QR создаётся из указанного владельцем публичного адреса. Генератор фотографий рисует только белую поверхность: настоящий QR наносится интерфейсом, имеет коррекцию H, белое свободное поле и небольшой лейбл SCENA в центре. Постер скачивается в PNG 1024 × 1536 с лейблом SCENA, именем и названием направления. На телефоне кнопка «Показать QR-код» открывает увеличенный код для сканирования. Адрес localhost относится к компьютеру, на котором работает сайт; для посетителей нужен доступный им адрес.

Созданы встроенным Imagegen. Для каждого нового владельца нужны его собственные исходные фотографии и отдельная проверка сходства; фотографии Марии нельзя автоматически выдавать за фотографию другого человека.

## Общая инструкция к каждому промпту

Use case: identity-preserve. Use the supplied original photographs of the same adult person as the identity reference. Keep recognizable facial proportions, eye shape, nose, lips, skin tone and hair. Do not replace the person with a generic fashion model. Portrait 2:3, full length head to shoes, photorealistic editorial quality. Leave the visible front face of the invitation prop fully white, facing the camera, without writing or an invented QR pattern. Keep hands on the edges. No text, watermarks or existing brand logos in the generated photograph. Add the actual SCENA QR and brand label separately after generation; verify scanning before sharing.

## Моя Сцена — личное знакомство

Premium personal invitation campaign photo. The person wears an elegant ivory trouser suit over a tasteful silk top. Natural confident welcoming pose, holding a beautiful matte white invitation square at waist level, straight towards the viewer, about 18% of the picture width. Deep black lacquer stage floor, a crescent of warm amber light, velvet shadows and mirror reflections. An intimate premiere mood presenting her personality, personal story and creative world. Keep the background almost black to all edges.

## Professional — приглашение к специалисту

Premium campaign portrait of the same adult makeup artist. Elegant sharply tailored black trouser suit, ivory blouse, full length beside a slim glossy black makeup console. Visible artisanal makeup brushes and a simple lighted mirror, no clutter. The artist holds a small beautiful square white placard at waist height, directed straight towards the viewer. Warm ivory theatrical mirror lights and subtle copper reflections on a shiny dark runway floor. Credible professional presence and a welcoming direct gaze.

## Model — белый куб на подиуме

A short contemporary light ivory dress on thin shoulder straps, opaque graceful flowing fabric, tasteful modern fashion styling and simple heels. She holds a beautiful satin-white geometric cube in both hands at waist level. Its front face is a perfect blank square directed at the camera, without perspective skew or covered corners. Black glossy runway, a tall architectural light arch behind her, narrow white spotlights and cinematic silver reflections. An intriguing warm confident look, full height and a subtle floor reflection. Identity likeness is the priority.

## Запись к мастеру — персональное приглашение

The same adult woman wears an elegant champagne silk midi dress with an ivory cropped jacket. She stands next to a beautiful empty modern makeup chair and invites the viewer to a personal appointment. A small square white appointment invitation is held straight at mid-torso, fingers only on the edges. Black lacquer stage floor, warm ivory spotlight, quiet sculptural champagne curtain folds and a dark reflective backdrop. Premium personal stage atmosphere, no other people. A welcoming natural smile that preserves the person's facial proportions.

## Проверка V1.7

- Четыре полных PNG-постера распознаны независимым декодером: каждый ведёт на своё направление.
- Коды с лейблом SCENA распознаны также для длинного тестового адреса.
- Увеличенные мобильные QR-коды распознаны для всех четырёх направлений.
- У Model QR находится на передней стороне куба; увеличение доступно по нажатию на куб.
- Реальная доступность адреса посетителю зависит от размещения конкретной установки; в этой сборке публичный домен не придуман.
