# Локальная контрольная точка dev96 — 13.10.2026

**Dev96 установлен: final pure8427/323, artifact и metadata83/27 приняты.
Internal positive native deletion завершился отказом независимой проверки
соседа после committed deletion; полная приёмка не принята. Отдельная
инспекция/очистка восстановила baseline; старый владелец завершён.**
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

Промежуточный live positive: parent независимый BASE/8000 подтверждён,
leaf callback начат, **leaf_prepare**, capture83/running, error отсутствует.
Это промежуточное состояние: actual deletion, terminal cleanup и baseline
этого dev96 ещё не приняты. Новые CAD-вызовы параллельно не запускались.

Подготовленный public native-owner callback использует исходные B1 HWND/
canonical/PID связи, независимые полные наблюдения и отдельный comparison operand
для своих annotation-view namespaces. Original durable jobs не переписываются.
Mapper проверяет оба actual observation hashes и локальные счётчики отдельно;
mapped revision выводится из actual metadata/counter, server revision не копируется.
Все snapshot rows, bindings, окна, файлы, application и соседи сравниваются.
Default native gate отвергает искусственную metadata из доменных fixtures.
Full public prerequisite требует actual positive/faults SQL и reports одного wheel;
historical unknown остаётся unknown/unresolved. Общий B2 gate не подменяется.

Итоговый связанный helper-набор: **694 passed /101,58 с**, без CAD. Последний
pure-пакет исходников MCP остаётся8427; helpers не потребовали новой установки.
Рабочая v1 и installed dev96 не изменены, пакетного push/CI ещё нет.

**Фактический отказ первого dev96 positive.** Actual leaf preparation succeeded;
delete succeeded/committed, replay вернул тот же job, original B1 SQL сохранён.
Полный committed BASE→SKETCH, surviving sketch/canonical/PID и target absence
присутствуют в SQL; native ledger содержит **14 парных событий**, все normally
returned. Всего parent записал112 нормально завершённых rectangle captures.
После этого `first_save_part_snapshot(neighbor)` отверг независимый full read
из-за изменения model/configuration/revision event envelope. Конкретный источник
изменения пока не установлен; отказ не переименован в успешную приёмку.
Первый отчёт и journal сохранены, read-only root audit подтверждает committed
job/replay и отсутствие active/unresolved SQL jobs; cleanup authority он не даёт.

Parent остаётся retained STA с собственными controls. Собственная очистка и
оригинальный baseline этого запуска не подтверждены; новые native-тесты,
повтор удаления и переустановка не запускались. Требуется инспекция удержанного
native-владельца и безопасное восстановление состояния по согласованным правилам.
Подготовленный public драйвер проверен фактическим failed report в установленном
интерпретаторе без source PYTHONPATH: **ожидаемый preflight refusal** до metadata
provider/CAD, без server/metadata-state. Это проверка защиты запуска, не public
native-приёмка. B2–B5 и стадия1 остаются открыты.

**Восстановление после отказа.** Read-only maintenance, по ранее принятому
процессу dev95, сверила исходные acknowledged HWND, complete current profiles,
родные PID/canonical membership и ревизии обоих собственных controls с committed
SQL. Два полных текущих capture совпали; все диагностические watches закрылись
со стабильными counters и без новых events. Это подтверждает текущее состояние,
но не объясняет и не отменяет прежний failed event envelope.

Оба контроля закрыты без сохранения, два CloseDoc normally returned с проверкой
retirement. Первичная финальная проверка cleanup использовала ошибочное прямое
сравнение Python tuple и JSON array. Отдельный read-only audit, без повторного
закрытия, сравнил полный baseline через точный JSON, подтвердил **0 документов,
CommandInProgress=False**, исходное application/non-STL preferences и неизменный
SQL. Cleanup/baseline приняты отдельно; positive native отчёт остаётся failed.
Idle retained Python runtime завершён только после этих доказательств; его
launcher тоже завершился, session12444 закрыта. Pending COM не отменялся.
Все11 original helpers сохранены в private архиве перед правкой оболочки.

Guard оригинального B1-владельца теперь reacquired **перед** independent
SKETCH/neighbor oracle, а не после них. Model/revision events по-прежнему
отвергаются. Успешный target readback сохраняется до отдельного neighbor read;
read progress/returned exception явно записываются, interrupt оставляет live
marker. Ни один такой marker не разрешает cleanup/retry. Добавлен отдельный
pure diagnostics helper для metadata/model/configuration/watch отказов, включая
ABA и неполный event trace; он никогда не даёт native/cleanup/retry acceptance.
Связанные tests positive/fault/preflight/diagnostics: **209 passed /78,03 с**.
Package/wheel не изменены; полный package-набор повторно не запускался.
Следующая positive приёмка использует fresh fixtures/journal, не старый запрос.

Guarded positive действительно запущен после отдельного принятого empty baseline
и завершения прежнего owner. Installed package/wheel тот же exact dev96;
metadata83 и origin снова подтверждены до CAD. Новый private state/journal и
новые controls; сейчас sketch_prepare/capture4 без ошибки. Running не считается
passed; старый failed positive, cleanup и архив helpers сохранены отдельно.

Следующее read-only наблюдение живого владельца показывает `extrusion_job`,
52 captures, последний ещё running, error отсутствует. Это только прогресс;
cleanup, fault-wrapper и public native до terminal positive не запускаются.
Во время ожидания подготовлена пассивная привязка отказа preview к actual SQL:
**22 pure passed /0,70 с** на искусственных заданиях с реальным SQLite. Никаких
COM-вызовов, изменений live helpers, package или wheel. Для dependent/equation
fixture полный current oracle пока не готов; N5 не accepted. Изменения локальные,
дополнительный push/CI не запускался.

Параллельный ограниченный fixture helper плоскости/unused equation/linked file
завершён и объединён с пассивным refusal validator. **77 related pure passed
/4,55 с**; original receipt/creation jobs сохранены, pending запрещает повтор,
точный native handle/геометрическая роль/PID и двусторонние зависимости
проверяются перед признанием fixture подготовленной. Full refusal oracle не
подменяется и остаётся open; эти helpers не изменяют текущий positive manifest.

Добавлены retained current-target и ancillary collectors N5. Их scope отделён
от BASE, фактические данные читаются текущими getters; новый/заменённый объект,
pending receipt, event change, неизвестная annotation/view или неполный native
массив не получают replacement data. **158 related pure passed /7,61 с**;
искусственные handles и реальные доменные registry/SQLite, без native запуска.
Session/neighbor/file before-after, terminal fixture journal и cleanup ещё
предстоит объединить в N5 driver. Full N5/B2/stage1 остаются open.
Последнее наблюдение текущего positive: отдельный B1 sketch/replay passed,
`extrusion_job`, 71 captures, последний running, error отсутствует.

После этого N5 collector дополнен exact optional plane-offset DIM и полными
display/annotation/view связями. Current session reader проверяет два исходных
model incarnations, native metadata/windows/files/UI/reference graph и весь
neighbor BASE дважды; связанный equation fixture-файл имеет отдельный exact
fingerprint. **232 related pure passed /12,01 с**, только искусственные native
handles и реальные source domain/SQLite getters. Source wrappers не разрешают
native acceptance/cleanup. Native refusal driver с request-wide events,
durable jobs/replay и terminal fixture cleanup ещё не завершён.
Текущий dev96 positive перешёл к `owned_cleanup`; leaf wrapper внутри него
выполняет `leaf_prepare`, error отсутствует. 83 rectangle captures, последний
normally returned. Живой вызов продолжается; terminal результат пока не принят.

**Итог guarded positive2: принят.** Process завершён нормально; leaf2/2 и parent4/4,
**4136,97 с**,112 normally returned captures. Read-only root audit actual SQL,
reports/helper hashes и current native baseline завершён exit0:6 succeeded jobs,
3 committed mutations,14 парных leaf events, тот же replay job, исходные
creation receipts/jobs сохранены. Independent target SKETCH/neighbor и own cleanup
подтверждены; сейчас0 документов/CIPFalse, original application/non-STL preferences.
Exact wheel96/f80ee6d/9088e018 неизменен. Failed positive1 не переписан.

N5 whole-request batch подготовлен: real JobRunner error schema, original BASE
preparation, actual durable preview/delete отказ и оба replay, два full session
captures + watches двух моделей на протяжении всей цепочки. Unknown/pending/
изменение событий не разрешают after-read/retry/cleanup. **331 related pure
passed /26,56 с**; source-only, native N5 ещё не запускался. Следом обязательный
finite native fault-wrapper dev96, затем N5/public; B2–B5/stage1 остаются open.

Finite fault-wrapper действительно запущен после принятого positive2 и отдельного
current empty-baseline audit. Positive report SHA/actual SQL/fixed helpers gate,
exact installed wheel и metadata83/origin приняты до CAD. Используется новый
private state/journal, sole native owner root; сейчас `fixture_creation`, error
отсутствует. Running не считается passed. Подготовка N5 CLI продолжается только
в исходниках;22 live fault helpers и установленный пакет остаются неизменными.

Последующее чтение работающего fault owner подтвердило `sketch_job`,14 captures,
последний running, error отсутствует. Параллельная N5 подготовка дополнила
current reference inventory: все engineering features, body и полный current
edge/face PID census с roundtrip существующего installed getter. Missing topology
прерывает capture. **80 related pure passed /11,31 с**; отдельный тестовый запуск
также обнаружил и устранил зависимость helper import от collection order.
CAD/пакет/22 frozen fault helpers не затронуты, отдельного push/CI нет.

N5 exact-wheel CLI и source callback завершены, **367 related pure passed
/79,97 с**. Один explicit fixture kind на fresh run, original registry/B1 owner,
actual setup checkpoint/paired ledger, полный current target+neighbor+files,
preview/delete/replay под whole-request watches и terminal own cleanup gate.
Neighbor comparison сохраняет current controls/views; проекция к parent
first-save удаляет только два документированных rectangle-added поля.
Whole B2/public acceptance не объявлена.

Actual installed negative preflight ожидаемо отклонил failed positive1 перед
COM: false live marker, owned=[], no creation returns/no jobs.sqlite. Metadata
SDK читался, CAD не выполнялся. Native N5 остаётся not_run до окончания fault96.
Сам fault96 продолжает работать: `sketch_job`,34 captures, error отсутствует;
его helper manifest/wheel не изменены. Следующие N5 случаи идут последовательно.

Пока fault96 выполняется, завершены две независимые installed metadata-only
проверки timings того же wheel: enabled/disabled и недоступный timing SQLite.
Обе приняты без CAD; при отказе telemetry mandatory journal schema3 сохранён,
jobs0/mutations0, настоящий `job_not_found` и invalid-filter contract сохранены,
SDK закрыт. Native B4/N6 и telemetry isolation при mutation/restore/hold не
объявлены пройденными. Последнее наблюдение fault96: `extrusion_job`,57 captures,
последний running, error отсутствует. Live helper manifest не изменён.

Последующее наблюдение живого fault96 owner: original B1 setup завершён,
полный leaf baseline прочитан, начат `leaf_stale`; completed cases ещё нет,
error отсутствует. Это running, не passed. Отдельная source-подготовка B3
добавила I01 document/feature/dimension/sketch routes и I03/I09/I10; related
результаты и ограничения указаны в B3_ACCEPTANCE_MAP. Installed wheel и22
fault helpers неизменны; source-preparation не закрывает native B3 или стадию1.

Первый finite fault case dev96 полностью прошёл: `leaf_stale` — expected
`stale_revision`, no checkpoint/native write, exact same-ID replay; полный
current baseline и original receipt сохранились. Owner перешёл к `leaf_foreign`.
Whole faults gate пока running, не accepted; новые native N5/public не запускаются.
I12 source-preparation завершена отдельно,402 related pure/25,79 с; exact wheel
и22 frozen fault helpers остаются неизменными. Actual native B3 gate открыт.
