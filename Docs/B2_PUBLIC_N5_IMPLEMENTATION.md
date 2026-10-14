# Остаток public N5 в B2 — 14.10.2026

Read-only аудит десяти связанных файлов выявил недостающий публичный сценарий.
Процессы, тесты и CAD не запускались. Общий B2 остаётся открытым; принятый
own-leaf positive не доказывает отказ на зависимостях и связанных уравнениях.

Пользовательский результат: preview/delete через установленный MCP объяснимо
отказывается от неподдержанного объекта, сохраняет модель и соседний документ;
повтор request_id не выполняет действие повторно. Только существующие три
контрольных случая: `child_plane`, `unused_equation`, `linked_equation`.

Каждый случай требует отдельного свежего прогона. Добавлять его после
`run_b2_positive()` нельзя: эта цепочка уже удалила исходное выдавливание.
Её конечный validator требует переход BASE→SKETCH и не принимает отказной
сценарий с сохранённой моделью. Positive validator не следует ослаблять.

| Остаток | Переиспользуемая основа | Конечный критерий |
| --- | --- | --- |
| Подготовка fixture в исходном installed child | `B2ImpactFixtures`, точные setup steps/receipts `OwnImpactHook`, public B1 construction и BASE preparation | Исходные registry/store/epoch; одна setup mutation succeeded/committed; exact paired native steps; приватный verifier seam без нового публичного fixture tool |
| Async public refusal chain | `public_invoke`, `job_get`, SQL validators `preview_refusal`/`execution_refusal` | Preview/replay/delete/replay через настоящий SDK; ровно две refusal rows и прежние operation IDs при replay; полный DTO/SQL binding |
| Наблюдение всего асинхронного запроса | `run_observed_refusal`, `B2ImpactSession`, два original event watchers | Watchers охватывают captures, awaits и replay; исходные model/configuration identities и pending gates; equal endpoints не скрывают ABA; unknown не допускает следующий CAD read |
| Отдельный конечный validator и driver | Supervision/cleanup исходного public B1 owner | Сохранная unsupported session, terminal process и journal, exact ownership cleanup/baseline; положительный validator удаления остаётся прежним |

Синхронный envelope сейчас отвергает coroutine dispatch. Вложенный event loop
и отдельная parent registry не заменяют исходное владение. В проверенных файлах
готовый child-owned fixture seam и async envelope не найдены; перед новой
реализацией проверить оставшиеся seams, чтобы избежать дублирования.

Приёмка каждого public N5 case требует exact installed wheel и исходной
ownership chain, нормального setup, четырёх публичных вызовов и двух новых jobs:
`leaf_deletion_unsupported` для плоскости либо
`first_save_snapshot_unsupported` для уравнений. Jobs terminal failed,
`requires_reconciliation=false`, mutation отсутствует; старые строки неизменны.
Target/neighbor/configuration/PID snapshots и события сохранены. Для linked
equation неизменны bytes/SHA, file identity и timestamps частного файла.
Нет active/unknown jobs, pending native steps или application hold; исходный
процесс нормально завершён, собственные документы закрыты, baseline и
согласованные non-STL настройки восстановлены. Случай не закрывает весь B2.

Порядок допуска: terminal faults prerequisite dev97 → три принятых internal
N5 → public positive и отдельные public N5. Текущий единственный native owner
ещё выполняется. Эта подготовка не разрешает параллельный CAD dispatch.
