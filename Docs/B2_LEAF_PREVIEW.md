# B2: подготовка удаления собственного конечного выдавливания

**Read-only preview, отдельная native receipt, durable executor и runtime/MCP
реализованы; dev96 artifact/metadata приняты, native-приёмка ещё выполняется.**
Эти файлы появились после сборки dev95 и не входят в его wheel.

Preview допускает только оригинальное B1-выдавливание из реального succeeded
creation job в текущем connection epoch. Две полные session-проверки, original
canonical/PID, actual GetChildren и полный dependency census должны подтвердить
несохранённый одноконфигурационный BASE без downstream/external/auxiliary связей.
Полный equation context читается с properties и rows; toy counts недостаточны.
Текущие глубина и русские имена берутся из фактического снимка. Borrowed sketch
остаётся исходным, изменения его геометрии/параметров дают отказ.

Результат содержит текущую revision, удаляемый feature object ID, сохраняемый
sketch ID, оставшиеся width/height и отсутствие тела после операции.
`delete_authorized=False`: preview сам не выдаёт полномочие на запись.
`native_execution_available=True`: исполнитель реализован; это не статус
native-приёмки. В каталоге зарегистрированы `feature_prepare_leaf_deletion`
и `feature_delete_leaf` (83 tools/27 mutations). Dev95 содержит прежние81/26
и не принимает эти последующие изменения. Dev96 установлен, metadata83/27
подтверждены. Guarded internal positive2 принят2/2 на exact dev96: actual
CAD deletion/SQL committed/replay и собственная очистка подтверждены.
Отказы/unknown faults1 приняты5/5; N5 и публичная MCP-цепочка ещё открыты.
[Конечная очередь и доказательства](B2_DEV96_REMAINING.md).

Полное постусловие BASE→SKETCH сочетает reverse extrusion proof и forward
session comparison: обратный proof отдельно не проверял фактический dirty
after-state. Все соседние файлы/данные/UI, sketch и ссылки сохраняются.

Для записи `NativeOwnedLeafDeletion` создаёт отдельную структуру receipt:
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

Executor использует durable application checkpoint и полный fresh revision,
paired guards/native ledger, затем current BASE/SKETCH census без вызовов
уже удалённого feature. Original sketch canonical/PID, raw old-feature PID
state1/4 +null, полное отсутствие target canonical и точный BASE→SKETCH набор
подтверждаются независимо. После commit аннулируются geometry aliases, только
удалённый feature reference/index и его ownership; sketch ownership сохраняется.
После доказанного удаления нет автоматического Undo, recreate или retry.
При неизвестном исходе сохраняется hold; original succeeded creation SQL/receipt
не переписываются.

Дополнительно прошли32 executor pure/12,17 с,91 facade pure/0,88 с и20
runtime pure/3,19 с. Они используют actual coordinator/JobRunner/SQLite,
NativeOwnedLeafDeletion и FastMCP/runtime, но искусственные native-состояния.
Первый объединённый прогон306 passed/1 failed обнаружил отсутствующие новые
имена в guide; guide исправлен, повторный связанный набор —349 passed/34,35 с.
Native/internal,
отказы/unknown и public MCP gates остаются обязательными отдельными задачами.

Positive-only native wrapper подготовлен:20 pure/0,68 с, без COM. Actual CAD
delete запускается только после независимой B1 BASE/8000 мм³/neighbor проверки
на том же wheel; original ownership не реконструируется. [Кандидат dev96](CHECKPOINT_DEV96.md).
