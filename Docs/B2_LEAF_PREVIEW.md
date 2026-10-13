# B2: подготовка удаления собственного конечного выдавливания

**Read-only preview и отдельная native receipt готовы в исходниках;
исполнитель/runtime/MCP и native-приёмка ещё не выполнены.**
Эти файлы появились после сборки dev95 и не входят в его wheel.

Preview допускает только оригинальное B1-выдавливание из реального succeeded
creation job в текущем connection epoch. Две полные session-проверки, original
canonical/PID, actual GetChildren и полный dependency census должны подтвердить
несохранённый одноконфигурационный BASE без downstream/external/auxiliary связей.
Полный equation context читается с properties и rows; toy counts недостаточны.
Текущие глубина и русские имена берутся из фактического снимка. Borrowed sketch
остаётся исходным, изменения его геометрии/параметров дают отказ.

Результат содержит текущую revision, удаляемый feature object ID, сохраняемый
sketch ID, оставшиеся width/height и отсутствие тела после операции. Пока оба
флага `delete_authorized` и `native_execution_available` — False. Инструмент не
зарегистрирован в публичном каталоге; preview не разрешает native dispatch.

Полное постусловие BASE→SKETCH сочетает reverse extrusion proof и forward
session comparison: обратный proof отдельно не проверял фактический dirty
after-state. Все соседние файлы/данные/UI, sketch и ссылки сохраняются.

Для будущей записи `NativeOwnedLeafDeletion` создаёт отдельную структуру receipt:
COM handles удерживаются, mutable metadata/annotation-view receipts копируются.
Original creation receipt не изменяется. Current viewport снимается заново;
creation-time viewport не навязывается пользователю. Одноразовый bridge использует
`restore_rectangle_extrusion`/`DeleteSelection2(0)`, сохраняющий borrowed sketch.
Exception-return не подтверждает pending COM/ledger и не разрешает повтор.

Проверки: **153 related pure passed /10,74 с** —39 full delta predicates,
102 real registry/SQLite/census preview с искусственными native-getters и12
receipt isolation/one-shot boundary cases. После добавления явного preview
удаляемого/сохраняемого набора повторён связанный каталог:102 passed/11,91 с.
Это source/artificial результаты; actual CAD deletion не выполнялась.

Остатки: доменный executor с durable application checkpoint; full current
post-deletion census без обращения к уже удалённому feature; original sketch
canonical/PID и actual raw old-feature PID state; exact removed set/cache
retirement; native/internal/public gates. После доказанного удаления нет
автоматического Undo, recreate или retry. При неизвестном исходе сохраняется hold.
