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
