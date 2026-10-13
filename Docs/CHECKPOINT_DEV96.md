# Локальная контрольная точка dev96 — 13.10.2026

**Dev96 установлен: final pure8427/323, artifact и metadata83/27 приняты.
Internal positive native deletion запущен; running не означает приёмку.**
Historical dev95 имеет принятый positive suppression/return; negative/public
и общий B2 gate открыты. [Привязка dev95](CHECKPOINT_DEV95.md).

| Привязка | Значение |
| --- | --- |
| Wheel | `solidworks_mcp-2.0.0.dev96-py3-none-any.whl` |
| Build Git SHA | `f80ee6d80819140a8122fcf26104b0ce6760bff8` |
| Wheel SHA256 | `9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa` |
| Source digest | `d861172b1437057a913c12ef7937a91eef7569deb7dd8ddae19d0d05a8655d59` |
| Каталог | 83 инструмента /27 операций записи |

Clean Git/source identity и архив wheel подтверждены artifact gate.
Установленный пакет проверен в `site-packages`, без source `PYTHONPATH`:
настоящий MCP stdio tools/list/system_get_info, schema hash и exact mutation
catalog совпали. Metadata не вызывала CAD. Установка изменена только в
dev-окружении; рабочая v1 сохранена.

Два source-инструмента: `feature_prepare_leaf_deletion` и `feature_delete_leaf`.
Каталог83/27, scope `owned_rectangular_leaf_extrusion_deletion_v1`.
Поддерживается только исходное серверное B1-выдавливание в текущем connection
epoch, активный несохранённый BASE одной конфигурации, исходный эскиз,
без дочерних элементов, equations/external/auxiliary dependencies.
Снимки соседей и всей поддержанной сессии обязательны.

Preview фиксирует текущую definition/revision и удаляемый/сохраняемый набор.
Executor использует отдельную receipt с текущим viewport и original native
handles, durable application checkpoint, paired guards/native ledger.
Original succeeded creation job/receipt не изменяются. Полный BASE→SKETCH,
текущий sketch canonical/PID, отсутствие target canonical и raw old PID
state1/4+null подтверждаются после normally returned native-вызовов.
После commit удаляются точный ownership/reference/index, geometry aliases
аннулируются; исходный sketch ID остаётся. Pending/unknown сохраняет hold
без Undo/recreate/повтора.

Связанные source-проверки: **349 passed /34,35 с** — executor/preview/receipt,
FastMCP/runtime, stdio discovery и metadata gate. Дальнейшие две fixture
уточнены под production `(NativeView, bound IFeature)` tuple shape; эта форма
проверена итоговым pure-набором. Первоначальный объединённый прогон306/1
выявил отсутствующие имена в guide; исправленный повтор349 принят.

Новый positive-only native wrapper прошёл **20 pure /0,68 с**, без COM.
Он вызывается перед первой собственной очисткой родительской B1 fixture,
после independent BASE/8000 мм³/neighbor proof. Использует original catalog/
SQLite/ownership, нормально возвращённую передачу собственного parent guard,
одну delete-операцию/replay и независимый surviving SKETCH readback.
Application проверяется canonical COM identity, а retained annotation views —
реальной tuple shape. Ошибка блокирует повтор и дальнейшую очистку; driver
удерживает STA/evidence. Это не native/public приёмка.

Полный pure-набор: **8427 passed /323 CAD deselected,260,01 с**.
Пропущенные CAD-случаи не засчитываются как native.

Native driver запущен на этом exact wheel одним COM-владельцем. До создания
контролей проверена исходная empty/free session; в первой записи отчёта нет
ошибок, fixture creation/capture выполняются. Helper/wheel не меняются во время
прогона. Terminal cleanup/baseline и actual deletion ещё не подтверждены.

Осталось: internal native deletion, конечные negative/unknown и
public MCP gates B2. Стадия1 и PR остаются открыты; пакетный push/CI не выполнен.

Во время live native готовятся отдельные verification helpers без изменения
package/wheel и hashes текущего драйвера. [Конечная приёмка N1–N6](B2_DEV96_ACCEPTANCE.md)
отделяет source/artificial evidence от installed/native и сохраняет все остатки.
Новый helper-набор прошёл239 pure/78,17 с: public contract/durable preparation/
lineage/ledger32, known-no-effect и terminal unknown fault hooks, passive exact
positive gate и безопасная own cleanup без reconciliation. Native fault-wrapper
не запускался. Работающий positive достиг extrusion job/capture53 без ошибки;
последний capture running, leaf callback ещё не начинался. Это progress,
не terminal/native acceptance. Установленный digest/wheel остаются прежними.

Подготовлена публичная цепочка preview/delete, не обращающаяся к CAD без
подключения единственного native-владельца. B1 bootstrap допускает ограниченное
продолжение после независимо подтверждённого BASE; исходный публичный B1 helper
сохранён отдельно с SHA256 из отчёта dev94. Стандартный B1 маршрут сохранён.
Новая цепочка требует полное состояние сессии и соседей, read-only preparation,
независимые доказательства размера/русского имени, suppression/return,
leaf preview/delete/replay и durable отказ чтения удалённого ID. Перед завершением
сверяются исходные записи журнала: replay не добавляет новый job и не меняет
прежние результаты, payload, digest или checkpoint. Неподтверждённое сравнение
удерживает supervisor; оно не превращается в право собственной очистки.

Связанный source-набор: **480 passed /43,29 с**. После последней защиты журнала
повторены затронутые route/bootstrap tests: **125 passed /10,97 с**.
Дополнительные helpers независимого наблюдения и scalar/rename входят в первый
набор. Это искусственные доменные наблюдения и транспортные проверки, не CAD.
Установленный package/wheel не изменён; все **11 hashes** live positive manifest
сверены с диском без расхождений. Публичный native-driver ещё не подключён.

Для public приёмки остаются явные технические gates: отображение document ID
только через удержанные canonical/HWND связи; доказанное сопоставление adapter-local
annotation view namespaces с сохранением исходных наблюдений; согласование
независимых observation counters/revisions без подстановки серверного baseline.
Недоказанное изменение annotation position/text после размера не поддержано
и не исключается из сравнения ради прохода теста.

Последний прочитанный live positive: parent независимый BASE/8000 подтверждён,
leaf callback начат, **leaf_prepare**, capture83/running, error отсутствует.
Это промежуточное состояние: actual deletion, terminal cleanup и baseline
этого dev96 ещё не приняты. Новые CAD-вызовы параллельно не запускались.
