# S1-B3: подключение конечного native-драйвера

13.10.2026. Все source-маршруты конечного manifest подготовлены. Это не
native-приёмка: фактические producers, setup transitions, namespace bridge,
public stdio и terminal cleanup остаются открыты. Граница — 13 групп и
27 tools из [карты приёмки](B3_ACCEPTANCE_MAP.md); новые инженерные операции
стадии2 сюда не добавляются. Единственный CAD-владелец — root.

## Source-маршруты и недостающие реальные доказательства

| Группы | Подключаемые scripts | Producer / конечный gate |
| --- | --- | --- |
| I01 | `verifier_b3_document_metadata`, `verifier_b3_part_objects`, `verifier_b3_rectangle_sketch` | Current original model/config anchors; независимые metadata/feature/dimension inventories и полный B1 rectangle snapshot. Actual `sketch_get` на same-wheel B1 пластине; просто старый clone snapshot не заменяет вызов tool |
| I02 | `verifier_b3_part_geometry` | Все original part body/face/edge PID и canonical membership; independent area/length; полный current inventory и closing scope |
| I03 | `verifier_b3_component_membership` | Original returned instance anchors и текущие opaque ID→native PID bindings; repeated model/config, nested parent, raw total transforms; 3/2/2 body rosters |
| I04 | `verifier_b3_rename_references` | Acknowledged actual Russian own rename, exact allowed-change scope и old-PID→same-canonical resolution; alias разрешён, имя не создаёт владение |
| I05 | `verifier_b3_component_retirement` | Две acknowledged owned native фазы delete/reinsert; original canonical absent, new normally returned own handle; whole transition scope. Critical paired receipts отдельно не принимают transition |
| I06 | `verifier_b3_configuration_references` | Acknowledged referenced/part configuration phases, old/current configuration incarnations, exact allowed-change scope. Body canonical может остаться прежним; context/opaque references должны соответствовать новой конфигурации |
| I07/I08 | `verifier_b3_part_mass`, `verifier_b3_part_bounds` | Actual native effective density/no overrides/selection и independent analytic bounds/support. Full scope/selection должны сохраниться; mass checkpoint committed |
| I09/I10 | `verifier_b3_instance_distance`, `verifier_b3_instance_point_axis` | Original normal solid census, actual native trimmed-boundary/location/axis witnesses; local/root/explicit frame transformations |
| I11/I12 | `verifier_b3_aggregate_distance`, `verifier_b3_aggregate_point_axis` | Полный leaf/body/face census, все native pair/probe receipts включая nonwinning и hidden. Surface-only refusal — отдельная acknowledged setup phase со свежими refs |
| I13 | `verifier_b3_replay` | Actual selected domain/solver counters того же owner epoch, whole unchanged journal/session. Эти counters не объявляются полным COM census |

## Последовательность подключения

Подготовлен actual child bootstrap `verifier_b3_stdio_bootstrap.py`. Он запускает
штатный installed `server_v2.main` с Runtime-наследником, не добавляя tools и
не меняя package. После normally returned `_execute` на том же STA экспортирует
существующие catalog ID/PID tables; дополнительных CAD getters не вызывает.
Приватная запись включает operation/arguments/result SHA/connection epoch.
Replay, не dispatch-ящий домен, не создаёт дополнительную запись. Ошибка или
исчерпание bounded sidecar не меняет публичный job/result: parent обязан
отвергнуть неполное доказательство. Terminal marker пишется только после
фактически подтверждённого Runtime shutdown, не после тайм-аута ожидания.

Bootstrap/export/namespace/Runtime related **52 pure passed /2,94 с** — реальные
Runtime/SQLite/catalogs, искусственный CAD-адаптер. Installed dev96 bootstrap
проверен отдельным metadata-only SDK:83 tools, exact schemas/build,0 runtime
trace records, штатное закрытие SDK/worker. Это не actual CAD registration export
и не приёмка B3. Parent original model/HWND mapping, current PID/owner roundtrip,
whole-session native envelope и подключение13 групп остаются обязательными.
Предыдущий full10220 checkpoint b842a9c не включает этот новый isolated helper;
installed package и31 frozen helpers текущего N5 не изменены.

Следующий bridge блок подключает optional native window mode bootstrap и
`ChildTrace` непосредственно к `B3Reader`. CLI получает original HWND roster
явно от fixture owner; child читает current model/HWND canonicals дважды вокруг
экспорта, не связывает документы по имени/пути. Raw окно — наблюдение, не proof
original birth/ABA/whole-session; эти flags остаются false и требуют parent gate.
Регистрационный режим по умолчанию по-прежнему не вызывает CAD getters.

Каждая запись теперь связана с единственным actual running SQLite job,
operation_id/request_id и точным payload SHA. В parent после coherent terminal
SDK/SQLite observation `ChildTrace` проверяет sequence, result/payload SHA,
неизменный epoch и полную ID/HWND/export таблицу. Replay повторно использует
неизменные исходные bytes, без нового trace/native dispatch. Повреждение или
неполный trace удерживает B3Reader/supervisor и запрещает дальнейший dispatch,
не переписывая успешно завершённый job и не разрешая cleanup.

Итоговый bridge/reader/journal/namespace/export related набор: **102 pure passed
/6,52 с**. Public facade→Runtime→SQLite→trace реально связаны в тесте, CAD getters
искусственные, supervisor также искусственный. Installed metadata-only smoke
нового bootstrap:83 tools/0 trace records, SDK/worker закрыты; actual CAD/HWND
capture не выполнялся. Current PID→original canonical/owner roundtrip,
whole-session envelope и fixture/13-group native driver остаются открытыми.

`PartReferenceBridge` теперь соединяет child document ID/HWND/PID с удержанными
original part/body/face/edge handles, затем вызывает direct native I02 observer.
Root проверяет весь текущий HWND roster и свою исходную model canonical
association до/после наблюдения. Для static I02 используется точный original
PID; rename/alias переход I04 остаётся отдельным маршрутом. Имена/форма/индекс
не создают владение. Полный owner/window/PID envelope закрывается последним
native event poll; closing owner admission также включён в metadata/event
envelope самого observer. **162 related pure passed /4,96 с** на actual catalog
registrations и artificial CAD getters. Native fixture/полный session observer,
запуск SDK→original CAD anchors и итоговая13-group приёмка ещё не выполнены.

Source part setup подготовлен в `verifier_b3_part_fixture.py`: два20×10×5 solid
при X0/40, sheet15×10 при X80, exact hidden второй solid, Основная/Вариант и dirty
сосед5×6×7. Только явный configured template, original owner/empty XY-plane
admission и paired durable callbacks; raw handles сохраняются до returned ack.
Любой pending/recorder loss/неподтверждённый результат удерживает caller receipt,
без retry/Undo/cleanup. Imported sheet связывается через normally returned
feature array [CreateSurfaceFeatureFromBody](https://help.solidworks.com/2020/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IPartDoc~CreateSurfaceFeatureFromBody.html),
после проверки временного sheet по native extrema; name-difference не используется.

Root review сохранил нормальный main/absorbed canonical traversal, ограничил
roster до identity callbacks и запретил naming template/sketch feature при
ложном returned feature. Fixture47 pure и integrated fixture/part bridge/
geometry/mass/bounds/reader **209 pure passed /5,01 с**, искусственные CAD getters.
Ни один actual fixture вызов в SolidWorks не выполнялся. CylinderØ12×30 и
same-wheel B1 sketch остаются отдельными fixtures, full session producer и
actual13-group/public driver остаются открытыми. Installed dev96 неизменён.

Связь completed part fixture с исходными I02 anchors подготовлена в
`verifier_b3_part_anchors.py`. Externally retained one-shot receipt принимает
только original Main configuration и3 target bodies либо1 own neighbor body.
Он читает полный native body/face/edge roster через original returned body
anchors, проверяет GetBody-владение и exact nonempty bytes PID/canonical
roundtrip, затем повторяет census и PID в closing envelope. Последний полный
census также охватывает изменение membership внутри closing PID getters.
Raw normal returns сохраняются до последующих getters; failures/owner loss
удерживают receipt и запрещают retry. Имена/форма/индекс/registration не
создают ownership. Полученный tuple OriginalPartObject предназначен для
`PartReferenceBridge` до SDK dispatch; cleanup/native acceptance остаются false.

Related anchors/bridge/fixture/native-part-reference: **199 pure passed /0,56 с**,
normal exit0. API-shaped artificial getters, Main44/neighbor19 anchors,
strict PID types во всех фазах, raw retention и final-census отказы проверены.
Это source-only блок после full10381/d974ffc, не входит в тот full-кандидат.
Actual setup/anchor capture в SolidWorks ещё not_run. Full session producer,
cylinder/same-wheel B1 sketch, namespace/SDK driver и13-group acceptance открыты.

Следующий source-блок соединяет empty-template admission с отдельным cylinder
fixture. `verifier_b3_empty_template.py` сохраняет все original template feature
anchors и native rigid frames до naming. Полный document roster должен точно
совпасть с исходными creation receipts; ранее созданные документы отдельного
builder допускаются только через completed `prior_fixtures`. Проверяются
единственные HWND, сильные model/configuration/feature canonicals, config ABA,
clean unsaved writable part, отсутствие тел/эскизов/dependencies и закрытый
owner/event envelope. XY выбирается по exact native identity transform,
Y-plane — по origin-centered native normal, не по имени/индексу.

`verifier_b3_cylinder_fixture.py` создаёт отдельный Ø12×30 cylinder вдоль
model-Y с одной конфигурацией Основная, как требует существующий I08 oracle.
Знак нормали исходной плоскости задаёт Dir выдавливания; native extrema должны
подтвердить bounds(-6,6,0,30,-6,6) мм. Original returned sketch/circle/feature,
три грани и единственное normal solid body сохраняются и проверяются до/после
rebuild. Raw returns предшествуют durable returned ack; pending/ledger loss
удерживают owner без retry/Undo/cleanup. Empty GetBodies2=None допускается
только для нового пустого baseline, не для созданного тела.

Root integrated admission→cylinder callback исполняет реальный source builder
и paired recorder на artificial API-shaped getters. Связанный admission/
cylinder/part-fixture/anchors/bridge/native-part-reference набор:
**395 pure passed /0,90 с**, normal exit0. Actual setup/admission/cylinder в CAD
ещё not_run; full10381/d974ffc не включает эти последующие helper блоки.
Initial application admission, whole-session producer, same-wheel B1 sketch,
assembly fixtures/transitions и actual SDK/13-group driver остаются открытыми.
Installed package и31 frozen helpers работающего N5 не менялись.

Первый concrete raw producer подготовлен в
`scripts/verifier_b3_native_part_reference.py`: прямые CAD getters для normal
solid/surface body, plane face и line edge конечного I02. Original retained
model/config/object/body canonicals и PIDs, полный normal-body census, current
membership, численные свойства и metadata/events проверяются независимо от
`adapter.geometry_summary`/public DTO. Admission предшествует даже canonical
equality; ordinals вычисляются внутри event envelope. **107 related pure
passed /4,20 с** на artificial API-shaped getters с реальным GeometryCatalog.
Actual namespace bindings/owner handles, whole-session watcher и real CAD run
остаются gates. Producer не подключается к occupied session и не разрешает
native acceptance/cleanup. Cylinder/curved-edge observers сюда не добавлены.

Direct producers I01/I03 также подготовлены:
`verifier_b3_native_document_metadata.py` читает retained model и все original
configuration anchors прямыми getters, включая inactive metadata без activation;
`verifier_b3_native_component.py` проверяет original PID/canonical census пяти
instances, referenced model/config, parent и raw16 total transform. Owner
admission предшествует native comparisons; ordinals и closing comparisons
входят в event envelope. **113 related pure passed /4,19 с** на API-shaped
искусственных getters и соответствующих routes. Actual opaque-ID bridge,
whole-session ownership/producers и installed CAD driver остаются открытыми.
Этот source-блок не входит в прежний full9952 checkpoint.

I01 direct feature inventory подготовлен в
`verifier_b3_native_feature_inventory.py`: bounded FirstFeature/subfeature
traversal со всем original retained canonical census/order, raw owner/error/
suppression/name/type и direct PID state0 roundtrip. Empty original PID явно
даёт unsupported row; исчезновение ранее поддержанного PID не скрывается.
После всех ordinal callbacks повторно читаются полный census и все raw facts;
closing metadata/events закрывают ABA. **70 related pure passed /1,58 с**,
API-shaped tree getters и прежние I01 routes. Dimension/display anchor producer,
whole-session owner/namespace bridge и actual installed driver ещё открыты;
новые CAD-вызовы этим source observer не выполнялись.

Namespace-side prerequisite подготовлен в
`verifier_b3_registered_references.py`: экспорт только уже существующих actual
catalog UUID/PID/compound dimension anchors, включая historical refs. Не вызывает
native getters/resolvers/_register, не создаёт таблицы и не принимает current
membership. **107 related pure passed /1,77 с** с реальными Geometry/Feature/
Dimension/Component/Topology registration tables и artificial adapters.
После финального ограничения topology kinds/явного current-membership=False —
12 targeted pure passed /0,14 с.
Подключение к actual SDK child, original document/window bridge и независимый
current PID→original canonical/owner roundtrip остаются обязательными gates.
Names/paths/shape не заменяют эти доказательства; private export не новый public tool.

Direct I01 dimension producer также подготовлен:
`verifier_b3_native_dimension_inventory.py`. Retained IDimension/IFeature и
display/slot/PID anchors, полный absorbed feature/display census, named-config
GetSystemValue3 без activation, независимые SI/mm/deg, tolerance/link/owner
facts и прямой/compound anchor. Annotation fallback допускает только точный
E_NOINTERFACE и проверяет обратную связь с display; иной native failure выходит
без retry. Полное повторное чтение после всех ordinals закрывает изменение
PID/owner/slot/raw facts. Agent targeted82 pure/0,18 с; root combined I01 getters,
routes/registration export — **164 pure passed /2,11 с**. Runtime typed BSTR,
native QueryInterface/slot associations, actual namespace/whole-session и
exact-wheel CAD driver остаются открытыми. Source-preparation не принимает B3.

После всей интеграции source observers/export на HEAD56fbc39:
**10149 pure passed,323 CAD deselected /526,73 с**, normal exit0.
Это [новая source checkpoint](B3_SOURCE_CHECKPOINT_DEV96.md); результаты9952
выше относятся к предыдущему fd43cc8. Installed wheel96/f80ee6d и30 helpers
текущего live N5 не изменены; full source run не является CAD-приёмкой.

Следующий namespace integration block после этого checkpoint:
`verifier_b3_native_namespace.py` связывает actual existing catalog entries и
UUID/PID exports с direct native current window/model census. Original explicit
HWND allowlist, один window на model, полный registry/census, два одинаковых
window bindings и два unchanged reference exports; closing event envelope
включает все canonical comparisons/owner callbacks. **155 related pure passed
/3,77 с**, actual catalogs и искусственные window getters; новый full-набор
после каждого helper не повторялся. Actual SDK child подключение, parent
original retained model/HWND proof и native used-PID owner roundtrips остаются
открыты. Collector не объявляет birth ownership/current object membership,
не создаёт IDs, не закрывает документы и не подключался к occupied SolidWorks.

1. До CAD принять exact installed wheel и metadata report. Offline dev96
   preflight уже принят:13 groups/27 tools, `can_start_native=false`.
   Не выполнять новые CAD-сценарии до terminal dev96 faults, root audit и
   собственной cleanup; далее обязательны N5/public B2 до итогового B3 gate.
2. Подготовить один original fixture owner для двух последовательных профилей
   part/assembly. Начальный roster, настройки, flags и files фиксируются;
   birth bindings сохраняются от нормально вернувшихся native handles.
   `session.py` содержит direct `AddComponent5` return до последующей настройки
   placement; driver должен удержать именно этот handle. Название, путь файла,
   placement или difference имён roster не принимают неизвестный объект.
3. Existing `verify_geometry_reads.fixtures` / component setup использовать
   как источник геометрии и проверенных сигнатур, не как готовый полный gate.
   Там есть поиск новой surface по имени и component role по path/placement;
   actual driver должен заменить такие bindings original creation receipts и
   current canonical/PID proof. Pending/exception оставляют outcome неизвестным;
   без retry, Undo, автоматического закрытия либо подстановки baseline.
4. Internal reads связывать с original catalogs/JobRunner/SQLite. Для public
   stdio opaque namespaces отличаются: нельзя подставлять internal IDs.
   Нужен private actual registration/PID bridge к тем же original native
   handles; unchanged names/paths/transforms не заменяют identity proof.
   Public schemas и штатные tool results сохраняются; новых production tools
   ради тестовой диагностики не добавлять.
5. Подключить producers к таблице выше и bounded `run_manifest`. Full current
   state читается независимо, до/после каждой необходимой цепочки; native
   watches закрывают ABA, metadata/config/selection/view/file/visibility и
   сосед входят в declared scope. Synthetic summary/complete flag не oracle.
   Подробные I04…I06 transitions не повторять в public без отдельного свойства.
   Текущий `execution_order()` требует independent controlled members для
   destructive transitions до measurements: metric fixtures сохраняются.
   Control births и их полный current scope должны быть явными в owner report,
   без добавления новых acceptance cases. Surface-only фаза I12 также требует
   собственного isolated setup; она не должна подавить solids metric-профиля.
6. Принять actual same-wheel reports всех13 групп, representative public
   routes всех27 tools, оба replay и coherent journal. После доказанной
   quiescence закрыть без сохранения только own terminal controls, восстановить
   own flags и проверить весь original baseline/non-STL preferences.
   Native acceptance возможна только после этих gates; исходники, offline
   preflight и pure tests сами её не дают.

Самостоятельный выбор безопасной собственной очистки уже разрешён пользователем.
Это не разрешает вмешиваться в live COM, пользовательские документы или
переписывать historical unknown. Реальные файлы/журналы остаются в private work.
