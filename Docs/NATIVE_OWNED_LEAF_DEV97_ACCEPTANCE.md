# Ограниченная positive-приёмка удаления leaf на dev97

14.10.2026 fresh native positive1 завершился normal exit0 за **6023,32 с**.
Приняты оба конечных условия positive: исходный own BASE→SKETCH с replay
без второй записи и delegated own cleanup с восстановлением baseline.
Это внутренний native prerequisite B2, не общая приёмка B2/public MCP/стадии1.

Точный installed кандидат: `2.0.0.dev97`, build Git
`49b899c9c6048c89be81e20c9c5c29f0e4ee50d4`, source digest
`ad83dc638a5df73c6511bf2d3d18600f82e2c299a235b86d8009ad3b0c513b36`,
wheel SHA `702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b`.
Source PYTHONPATH не использовался; рабочая v1 сохранена. Короткий прежний
owner/prefix probe остаётся отдельным доказательством совместимости.

| Факт | Подтверждение |
| --- | --- |
| Исходный объект и подготовка | Original creation receipt/ownership, exact feature PID/document/configuration/revision; prepare succeeded |
| Фактическое удаление | Delete succeeded/committed; retained original sketch, retired feature PID и независимый surviving-sketch/neighbor readback |
| Повтор запроса | Тот же сохранённый job/result, без второй записи; creation receipt не переписан |
| Actual journal | 6 terminal jobs,3 committed mutations; активных/unknown/unresolved checkpoints в этой БД нет |
| Окончание native | Parent и leaf reports terminal, native_calls_live=false; исходный process exit0, pending/retained calls отсутствуют |
| Очистка | Собственные документы закрыты без сохранения, owned_documents=[], own_cleanup_verified=true, baseline_restored=true |
| Настройки | Исходная application/session и согласованный non-STL baseline подтверждены; deferred STL scope не объявляется восстановленным |

После выхода процесса проведён отдельный пассивный audit: текущая installed
identity/wheel, exact report/parent/helper hashes и реальные SQLite rows прошли
штатный positive_preflight без COM и нового сервера. SHA leaf report:
`f2fdfd231a1e0b9aed84e1d5e8760821a23ac6ac80191dae88dfc23e93807fc6`.
Полные отчёты/журналы и CAD-файлы остаются в private ignored work/.

После этого начат fresh faults1 на том же wheel с exact positive report gate.
Его итог pending. Finite N5 child_plane/unused_equation/linked_equation,
публичная цепочка и общий B2 остаются открыты в [очереди](B2_DEV97_REMAINING.md).
Dev96 positive/fault receipts не переносились; прежние unknown не повторялись.
