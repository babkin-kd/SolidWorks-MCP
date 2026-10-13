# Локальная контрольная точка dev95 — 13.10.2026

**Suppression реализован, первая native-попытка отказала до записи. B2 и стадия1 открыты.**
Публичная приёмка MCP и preview/delete ещё не выполнены; main/PR не приняты.

| Привязка | Значение |
| --- | --- |
| Wheel | `solidworks_mcp-2.0.0.dev95-py3-none-any.whl` |
| Build Git SHA | `08319cc77d678387c05e40db4833806f2f771ca9` |
| Wheel SHA256 | `8567dc3d65a8499ea8c92032e7f5c671f3abf7acfea9388b9f2ae5a84060dd06` |
| Source digest | `ed5f159268f5be232e41396a7b8ef3106aab9d42d89b6ac90ee0174172693d37` |
| Каталог | 81 инструмент /26 операций записи |

Реальные production domain/runtime/MCP для `feature_prepare_suppression` и
`feature_set_suppressed` используют original retained ownership B1 и явную
полную revision. Поддерживается собственное blind-основание несохранённой
одноконфигурационной детали. Текущие DIM/annotation/inventory поля читаются
из CAD, без заполнения baseline-данными. Возврат проверяет весь исходный BASE;
имя тела исправляется отдельно только после полного name-only proof.
Setter/rebuild/guards журналируются по pending/returned, inverse имеет свои
одноразовые метки. Unknown/pending не повторяется. Геометрические ID после
перехода, включая восстановленный или неопределённый, аннулируются.

Полный исходный pure-набор: **8111 passed /323 CAD deselected,236,53 с**.
Предыдущий полный прогон:8109 passed/2 failed из-за старых metadata fixtures и
версии непубликуемого registry template; ошибки исправлены, полный набор повторён.
Доменные34 теста используют реальные coordinator/JobRunner/SQLite и искусственные
native-объекты. Их результат не означает фактическую CAD-операцию.

Artifact gate и installed metadata/stdio **приняты**; `site-packages`, exact
version/Git/digest подтверждены без source `PYTHONPATH`. Metadata не вызывала CAD.
Wheel установлен только в dev-окружение, отдельная рабочая v1 сохранена.

Internal positive native driver запущен на этом точном wheel. Он использует
существующую B1 fixture/cleanup-цепочку, затем реальный suppression domain с
повтором request_id. Running не засчитывается как passed. Исходный empty/free
baseline проверяется до создания контрольных моделей; только root владеет COM.
Public MCP, отрицательные native gates и общий B2 gate ещё нужны.

Первая попытка завершила сценарий отказом через **383,79 с** в
`sketch.prepare_rectangle`: полный снимок соседней детали обнаружил изменение
native model/configuration/revision events. Реальный SQLite содержит один
terminal failed read-only job, **0 мутационных checkpoint**. Создание эскиза,
выдавливания и suppression через домен ещё не вызывались. Driver удерживал
свои два контроля и idle STA; это не running приёмка и не native success.

Root отдельно подтвердил quiescence и два стабильных полных исходных профиля.
Единственная разница между адаптерами — случайный adapter-local `av_UUID`
singleton annotation view: его полные данные и dimension bindings совпадают.
Ремап использован только в независимом cleanup comparison, не в production
mutation gate. Только после этих доказательств завершён известный idle worker.
Два собственных контроля закрыты без сохранения, empty/free baseline,
application context и non-STL preferences подтверждены. Original failed report
и отдельные quiescence/cleanup receipts сохранены; failed не переименован в passed.

Параллельно в игнорируемом `work/` подготовлен pure прототип BASE→SKETCH удаления
leaf extrusion:40 passed/1,48 с. Обратный extrusion oracle дополнен forward
session check; prototype не даёт права native dispatch и не входит в wheel95.
Далее нужны durable ownership/PID/children/revision, собственная deletion receipt,
native ledger, точный удалённый набор и retirement handles. Original creation
receipt нельзя изменять или использовать как текущую definition.

Связанные изменения зафиксированы локально. Отдельного push/CI нет; пакетная
отправка сохраняется после требуемой локальной/native-приёмки.
