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
