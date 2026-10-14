# Оставшаяся приёмка B2 на dev96

Контрольная очередь от 14.10.2026. Объём B2 не расширяется: изменение длины
и имени, подавление/возврат, preview/delete собственного конечного элемента
без зависимостей. Произвольное удаление графа остаётся D2-DELETION.

Точный installed кандидат: `2.0.0.dev96`, build Git
`f80ee6d80819140a8122fcf26104b0ce6760bff8`, wheel SHA256
`9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa`.
Публичный каталог — 83 инструмента /27 операций записи. Исходники в
`PYTHONPATH` не используются для installed/native приёмки.

| Блок | Пользовательский результат / поддерживаемый случай | Конечные критерии | Фактический статус |
| --- | --- | --- | --- |
| Положительное preview/delete | Удалить собственное конечное выдавливание, сохранив его эскиз и соседнюю деталь | Точный BASE→SKETCH, старый PID недействителен/null, SQL committed, replay без повторной записи, полный baseline после собственной очистки | Принят guarded positive2: 2/2, 4136,97 с; первый failed отчёт сохранён отдельно |
| Конечные отказы и unknown | Получить объяснимый отказ для stale/foreign/no-effect; не повторить запись при потере наблюдения | Все 5 случаев, фактический SQLite, неизвестное задание остаётся unresolved, новый запрос блокируется, собственная очистка и baseline | Принят faults1: 5/5, 9137,84 с |
| N5 — дочерняя плоскость | Не удалить выдавливание, от которого зависит собственная плоскость | Setup succeeded/committed; preview и execute возвращают `leaf_deletion_unsupported`; оба replay не вызывают домен повторно; полные before/after, сосед, PID/владение и event envelope неизменны; terminal cleanup/baseline | Третий прогон failed, own cleanup/baseline подтверждены; explicit body binder затем проверен короткой native-пробой. Четвёртый failed до preview/delete: returned persistent_reference_mismatch для dimension owner. Все6 native setup pairs/84 captures вернулись, SQL6 без активных jobs, unknown/unresolved сохранён. Independent own inspection, закрытие2 controls и baseline подтверждены; короткие probe1/3/4 mismatch не воспроизвели. Требуется диагностика конкретного dimension/anchor; N5 не принят |
| N5 — неиспользуемое уравнение | Отказать для модели вне ограниченного полного oracle, даже если величина не используется | Те же четыре запроса и проверка сохранности; ожидаемый отказ `first_save_snapshot_unsupported`; normal paired setup, фактический журнал, полный baseline | not_run; отдельный свежий прогон после завершения текущего владельца |
| N5 — связанный файл уравнений | Сохранить связь и частный файл при отказе preview/delete | Условия предыдущей строки плюс полное наблюдение связи, identity/timestamps/bytes/SHA файла до/после | not_run; отдельный свежий прогон после предыдущего |
| Публичная MCP-цепочка | Изменить толщину до 12 мм/9600 мм³, русское имя, подавить/вернуть и удалить собственный leaf через штатные инструменты | Все пять конечных public cases, opaque ID mapping к исходным native объектам, реальные SQL/replay, independent full observer, исходная сессия после очистки | not_run; driver подготовлен, внутренние gates выполняются первыми |
| Общий B2 gate | Принять все шесть условий блока в заявленном объёме | Согласованная сводка одного wheel: результаты, журналы, ограничения, native-постусловия и пакетный CI | Открыт; ни один отдельный accepted case его не заменяет |

После каждого native-прогона сначала проверяются terminal отчёты, фактический
SQLite, зафиксированные hashes helpers, отсутствие pending/retained вызовов
и восстановление исходного состояния. Следующий COM-владелец запускается
последовательно. Тайм-аут ожидания не отменяет текущий вызов. Прежние unknown
задания не повторяются и не переименовываются в success.

Перед очередью выполнена дополнительная пассивная проверка без подключения
к SolidWorks: exact installed wheel, positive/fault отчёты и их реальный SQL
подтверждены; historical unknown остался unresolved; все 31 helper текущего
N5 совпали с manifest. Полные доказательства остаются в игнорируемом `work/`.
Этот preflight не принимает текущий native-прогон и не разрешает его очистку.

После исправления current-body binder выполнен реальный верхнеуровневый
public preflight на тех же positive/fault отчётах и SQLite, с повторной
проверкой installed identity/wheel и повторным использованием metadata83/27.
Gate прошёл без COM и нового сервера; historical unknown остался unresolved.
Это пассивная подготовка, не разрешение запуска до завершения очереди N5.

Public completion теперь требует непустой список нормально возвращённых
native captures: пустой список, неверный тип и неполные rows не принимаются.
Связанные driver/route проверки: **120 pure passed /12,07 с**, normal exit0,
без CAD. Исправление не входит в32 frozen helpers live N5 и не изменяет wheel.

После own cleanup child-plane-4 и коротких probes fresh child-plane-5
завершился failed до preview/delete. Python-only диагностика указала
plane_offset/current_capture/current_anchor; создание первичного anchor
размера новой плоскости вернуло persistent_reference_mismatch. Все84 captures
и6 setup pairs вернулись; SQLite6 terminal jobs, setup unknown/unresolved.
Independent own inspection и cleanup завершены: закрыты две собственные
детали, baseline/CIPFalse/non-STL восстановлены, historical SQL неизменён.
Короткий probe6 failed до создания плоскости из-за Python assertion в выборе
размера; own cleanup/baseline подтверждены. Fresh probe7 завершился normal
за67,54 с: две fully-defined детали, четыре фазы,15 current dimension anchors
и retained anchors разрешились без owner mismatch;55 native steps вернулись.
Собственная очистка и baseline подтверждены. N5 mismatch не воспроизведён;
unknown N5 job не повторялся. Длительный N5 не перезапущен.
Root148 related pure и source4ec13fb full11271 остаются source evidence;
N5 не принят, unknown и обязательные remaining gates не меняются.

Следующий длительный N5 не запускать только на основании successful short
probe: сопоставить его owner/anchor факты с точным boundary child-plane-5.
Preview/delete остаются запрещены до terminal succeeded/committed setup.
После принятого child-plane выполнить два отдельных finite equation cases,
затем публичную цепочку и общий B2 gate. Новые классы зависимостей не добавлять.

Source-кандидат `c229bc4` объединяет четыре подготовительных блока B3.
Один итоговый pure-набор завершился normal exit0: **11054 passed,323 CAD
deselected /465,28 с**, CAD-фильтр и внешний basetemp; executable source/tests
не менялись во время проверки. [Сводка пакета](CHECKPOINT_C229BC4.md). Эти source-проверки не
подменяют native B2 или будущую приёмку B3. Пакетный push/CI выполняется после
необходимых локальных проверок; PR15 остаётся draft до общей приёмки.

Исходные результаты: [B2 dev96](B2_DEV96_ACCEPTANCE.md),
[совместимость возврата плоскости](B2_PLANE_RETURN_COMPATIBILITY.md),
[совместимость возврата тела](B2_BODY_RETURN_COMPATIBILITY.md),
[dimension-owner диагностика](B2_DIMENSION_OWNER_DIAGNOSTIC.md),
[аудит плана](PLAN_STATUS_AUDIT.md).
