# Ограниченная явная активация детали — S1-B5-ACT

**Исходная реализация подготовлена, native-приёмка не завершена.** Задача
входит в минимальную цепочку стадии 1: открытие L2 сохраняет исходную активную
модель; следующий dimension edit требует активного целевого документа.
Контракт L2 и его manifest не меняются. Широкая активация — D2-DOCUMENTS.

## Результат и поддержанные случаи

`document_prepare_activate_part_native(request_id, document_id, configuration)`
возвращает полную ревизию `native_rectangular_part_activation_v1`.
`document_activate_part_native` получает те же явные параметры и
`expected_revision`; `timeout_s` ограничивает ожидание, но не отменяет COM.

Цель уже открыта, видима, доступна для записи, имеет одну конфигурацию,
одно самостоятельное прямоугольное blind-основание и одно окно. Каждый сосед
должен допускать тот же полный passive part oracle. Внешние ссылки, неполный
снимок, read-only цель, иной профиль, несколько конфигураций и неоднозначный
native title отвергаются. Имя не выбирает цель: оно проверяется после разрешения
явного ID и используется только зарегистрированным native мостом.

Активным становится точный документ; конфигурация не переключается. Остальные
данные, геометрия, ссылки, dirty flags, файлы, selections/view, roster, CWD
и настройки сохраняются. Уже активная цель даёт независимо проверенный no-op.

## Гарантии и протокол

Полный checkpoint предшествует guard и native эффекту. После owned UI release
повторно проверяется вся ревизия. `ActivateDoc3` вызывается один раз через
exact native receipt; native bridge проверяет returned/active identities.
Нет обратной активации при неподтверждённом результате.

Owned guard освобождается **до** финального verdict. Независимый полный снимок
после освобождения, normal receipt и доказательство release необходимы для
committed. Это предотвращает зачёт предварительного снимка при позднем
изменении selection/view или данных. Потеря journal/release ACK сохраняет hold.
Guard release никогда не повторяется после попытки с неизвестным исходом.

Структурированный нормальный native error допускает known no-effect только
при полном совпадении исходного состояния и независимой проверке после release.
Throw/lost/malformed ACK либо реальный неподтверждённый эффект остаётся unknown.
Прежний job возвращается при replay; новый request/epoch не обходят application
hold. Очистка owned guard не превращает неизвестное задание в успешное.

## Конечная приёмка

| Условие | Доказательство | Слой |
| --- | --- | --- |
| ACT-N1: активация неактивной цели | Exact active-after; полный target/dirty-neighbor oracle и файлы неизменны; guard освобождён, post-release proof | Native установленного wheel; публичный MCP подтверждает контракт |
| ACT-N2: уже активная цель и replay | Независимый no-op, ноль новых activation calls; повтор request без второго эффекта | Internal/native и public journal |
| ACT-N3: неправильный/устаревший контекст | Чужой ID/config и реальное изменение supported baseline после prepare отвергнуты до activation | Native; остальные unsupported вариации — pure |
| ACT-N4: неподтверждённый исход | Controlled bridge failure после настоящего normal native call отдельно помечен; unknown/hold/replay, нет inverse/retry; независимые terminal witnesses и exact reconciliation | Internal native плюс pure receipt/guard/journal fault-набор |
| ACT-N5: очистка и точный артефакт | Только свои terminal fixtures, original baseline/CWD/preferences, exact installed wheel/version/Git/source/hash без source PYTHONPATH; metadata/stdio | Installed/native |

Для завершения нужны все пять условий; отдельный positive не закрывает задачу.
Искусственная вариация не выдаётся за фактическую ошибку COM. Сохранённые старые
wheel-отчёты относятся к своему коду; новый кандидат требует своих свидетельств.
После ACT остаются public L3-P1 и итоговая same-wheel B5 всей стадии.
