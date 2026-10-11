# Конечная матрица стадии 1 и перенос расширенных требований

Срез 11.10.2026. Новая граница выпуска — **семь обязательных блоков** L2, L3,
S1-B1…S1-B5 и законченный пользовательский сценарий. Старые S1-01…S1-22
сохранены как трассировка; прежний агрегат «20 из 22» больше не определяет
готовность. Перенос широкой поддержки — явная незавершённая задача стадии 2/3,
а не passed и не удаление требования. [План](../PLAN.md),
[точные условия приёмки блоков](STAGE_1_BLOCK_ACCEPTANCE.md).

**Фактический L2 dev87:** metadata71/21, source pure5560 passed/323 CAD
deselected (77,43 с). Final internal13/13 (210,07 с), public MCP11/11
(189,68 с), оба accepted=true на одном exact installed wheel/final helper hashes.
Own cleanup, полный baseline/CWD и dirty сосед сохранены.
Whole failed internal1/2 и прежний unknown dev86 сохранены отдельно;
[точная приёмка](NATIVE_DOCUMENT_OPEN_ACCEPTANCE.md).
**L2 закрыт в прежнем scope. Остались шесть блоков L3/S1-B1…S1-B5; стадия1 открыта.**

## Законченный пользовательский результат

При открытой dirty соседней детали: русская новая деталь → явно выбранная
native-плоскость → прямоугольный «Эскиз основания» 40 × 20 мм → «Основание»
10 мм → изменение толщины до 12 мм/9600 мм³ → первое сохранение нового
`.SLDPRT` → точный close/open → свежие ссылки, толщина 14 мм → Save3,
независимый native/disk readback 11200 мм³ → close. Соседний документ, его
несохранённые данные, geometry/config/references/selection/view и bytes файла
сохраняются; active и application settings/CWD возвращаются к baseline.

Минимум first save — собственная unsaved part с одной конфигурацией, одним
solid и без внешних ссылок. L2 сохраняет **уже разработанную** конечную область
part/assembly/drawing resolved с new/borrowed references, read_only,
replay/stale, clean rollback и CWD. Новые load/reference modes сюда не добавляются.

Для first save и финальной цепочки сосед ограничен самостоятельной контрольной
part того же наблюдаемого профиля. Гарантия сохранности полна в этом scope;
произвольные соседние модели не обещаны. Неподдержанный сосед или неполный
снимок блокирует запись. L2 сохраняет собственный уже принятый resolved scope.

## Обязательные гарантии: область поддержки ограничена, наблюдение полно

- Явные IDs/config/revision/request_id, единицы и coordinate frame по контракту.
  Native activation допускается только с заданным active-after и доказательством.
- Полный checkpoint/двойное наблюдение всей **поддержанной** области: модели,
  геометрия, конфигурации, пути/handles/references, окна/UI, файлы и настройки,
  которые операция способна затронуть. Неполный inventory блокирует запись;
  narrowed scope не даёт права выкинуть неизвестное поле или чужую модель.
- Один STA, durable pending/returned и holds; timeout не отменяет COM, replay
  не повторяет запись. Pending/unknown не повторять и не превращать в success.
  Holds сохраняются после restart/reconnect; reconciliation имеет точный proof.
- Независимые postconditions/native readback/rebuild. Known rollback требует
  доказанного восстановления; generic Undo его не заменяет. Cleanup только
  exact-owned terminal fixtures; unknown журнал не переписывается после очистки.
- Native accepted gates точного installed wheel отдельно от source pure и
  metadata. Skipped/running/failed/cleanup не засчитываются как пройденные.
- Русские имена новых деталей/элементов с native readback; стабильные ссылки
  не зависят от имени. Рабочая v1, user CAD/правки/шаблоны/PDM защищены.

Все гарантии обязательны и при сокращённом списке продуктовых случаев.
Расширенная возможность поддерживается только после отдельного блока с этими
же гарантиями. Unsupported отказ — доказательство защиты, а не реализации.

## Семь обязательных блоков: результат, конечная проверка, блокер

| ID | Поддержанный результат | Конечная приёмка | Факт и оставшийся блокер |
| --- | --- | --- | --- |
| L2 | Exact resolved native open part/assembly/drawing; new/borrowed closure/config, read_only; dirty baseline, clean rollback, CWD | Фиксированные 13 internal / 11 public cases текущего [контракта](NATIVE_DOCUMENT_OPEN.md): exact source/refs/ACK0/0/final oracle, stale/replay, normal failure/real missing receipt, Python failure после native, clean rollback и restored application context | Закрыт dev87 internal13/public11: accepted, own cleanup/baseline подтверждены. Исторические failures сохранены; новые load/reference modes — D2-LOADREF |
| L3 | Own unsaved part, одна конфигурация/solid, без refs: первый новый native путь без overwrite и доказанная live identity/path | Native success с независимым disk/reopen proof; existing-target и destination-race отказ без перезаписи; stale/foreign/replay; normal/pending failure с journal/hold и exact cleanup. Протокол публикации/замены identity сначала доказывается, не предполагается | [Source-прототип в работе](NATIVE_FIRST_SAVE_PROGRESS.md): related419 pure, реальный passive source capture двух деталей и NTFS6/6 на синтетических файлах. Clone/identity mapping, интеграция/installed/native ещё не приняты. Нет публичной регистрации. Save3 dev82 не является first save |
| S1-B1 | Русская новая part из пустого настроенного шаблона 1cfg; явная существующая плоскость; прямоугольный 2D-эскиз; одно blind extrusion | Positive chain 40×20×10/BREP/8000 мм³; foreign plane/context, stale и replay; known failure после настоящего создания с owned restore. Полное наблюдение своего простого графа | dev41/dev49 — история. Завершить явные контракты самостоятельных базовых операций и принять текущий wheel; add_plane/arbitrary profiles отдельные D2-GEOMETRY |
| S1-B2 | Driving length собственного основания; rename; suppress/unsuppress; impact preview/delete собственного leaf в полностью наблюдаемом простом графе | Readback 10→12 и BREP/9600 мм³; русское имя/stable ref; suppression flags+geometry; preview без записи, execute exact IDs; foreign/stale/dependent/incomplete inventory отказы; известное scoped restoration | Исторические размеры/rename частично приняты; suppression/delete ещё не имеют законченной общей приёмки. Generic dependent delete и signed/angle/tolerance — D2-DELETION/D2-DIMENSIONS |
| S1-B3 | Body/face/edge/sketch/feature/dimension IDs простой детали и уже поддержанные resolved instance paths; mass/bounds/distance в объявленных frames | Exact membership/units/PID roundtrip; renamed ref сохраняется, deleted/recreated/foreign/config mismatch отклоняется; аналитические mass/bounds/distance, selection preserved; stale read/revision. Проверить поддержанные current catalog scopes, не создавать новые frames/режимы | Scoped dev3/dev71–dev79 — история. Нужен конечный coverage текущего wheel; arbitrary frames/load states/1000+ — D2-FRAMES/D2-LOADREF/D2-LARGE |
| S1-B4 | Штатная bounded диагностика и безопасное восстановление job/hold | Installed late result/replay/conflict/queued cancel/restart unfinished→unknown/no retry; hold reconnect и exact reconciliation; known restore реального scalar/create; реальные исходные/новые rebuild дефекты поддержанной fixture различаются; timing actual chain, enabled/disabled/error isolation | Dev69/scoped journal — история. Не закрыты finite restart/recovery и фактические rebuild/postcondition gates. Панель мониторинга/full COM census не требуются |
| S1-B5 | Вся пользовательская цепочка create→edit→first save→close/open→edit/Save3→close при dirty соседе | Один финальный installed wheel/MCP stdio; native disk/readback, active/CWD/full dirty-baseline; exact-owned cleanup; finite cases→block IDs манифест, source pure/metadata и пакетный обязательный CI | L2 принят отдельно; L3/B1–B4 и итоговая same-wheel приёмка ещё не закрыты. Не суммировать старые wheel, не требовать всех unsupported CAD modes |

Точные случаи и stop conditions задаёт [STAGE_1_BLOCK_ACCEPTANCE](STAGE_1_BLOCK_ACCEPTANCE.md).
При выявленном дефекте исправить обязательный supported case. При новой
возможности создать/использовать задачу ниже: это не дополнительный gate текущего L2.

## Порядок и конечные условия снятия блокеров

| Очередь | Блок | Что снимает оставшийся блокер |
| --- | --- | --- |
| Завершён | L2 | Уже имеются accepted internal13/public11, exact wheel и baseline; дополнительные load/reference modes сюда не добавляются |
| 1 | L3 | Полный source/clone proof поддержанного профиля, no-overwrite публикация и live ID mapping интегрированы; конечные P/I/N gates приняты. Copy/NTFS/source-пробы по отдельности недостаточны |
| 2 | S1-B1 | Отдельные явные контракты plane/sketch/blind extrusion доведены до пользовательской цепочки и конечных P/I/N gates без добавления auxiliary planes или произвольных профилей |
| 3 | S1-B2 | Driving length/rename/suppress/unsuppress/own-leaf preview-delete проходят шесть условий своего контракта; точные survivor/retired sets и восстановление подтверждены |
| 4 | S1-B3 | Конечный manifest существующих supported reads связан с текущими IDs/frames и независимыми аналитическими результатами; новый topology/load/scale scope не требуется |
| 5 | S1-B4 | Доказаны шесть условий job/rebuild/recovery/diagnostics на установленном кандидате; реальный late result отделён от искусственных отказов, restart не обходится новым request_id |
| 6 | S1-B5 | Все предыдущие блоки имеют свои свидетельства; вся цепочка, cleanup и четыре release gates приняты на одном финальном wheel, обязательный CI пакета успешен |

P/I/N и точные числа условий заданы в [приёмке блоков](STAGE_1_BLOCK_ACCEPTANCE.md).
Этот порядок не разрешает переносить safety в S1-B4: каждая запись с первого
блока обязана иметь explicit target/revision, журнал и доказанные постусловия.
Расширение тестовой выборки оправдано изменением общего контура или найденной
регрессией; новая возможность получает отдельную видимую задачу ниже.

## Трассировка всех прежних 22 требований

В таблицах B1…B5 — сокращения точных ID S1-B1…S1-B5.
Колонка PLAN сохраняет нумерацию прежних разделов 1.1–1.5 для трассировки.
В колонке «стадия 1» — обязательная часть. В последней — широкая часть старого
требования, **перенесена, не выполнена**. У строк нет общей отметки passed:
исторические принятые scopes учитываются отдельно, блоки выпуска ещё открыты.

| Старый ID / PLAN | Обязательная часть стадии 1 | Широкий остаток, ID / целевая стадия |
| --- | --- | --- |
| S1-01 /1.1-5 | S1-B5: воспроизводимый wheel, build identity, fork PR и обязательный CI | D2-DISTRIBUTION /2: собственное публичное имя/публикация отдельным согласованным выпуском |
| S1-02 /1.2-1,1.4-5 | B5: каталог/guide/migration соответствуют installed реализованным tools; каждая legacy строка имеет owner/status | Исторический dev82 catalog proof не распространяется на новый wheel; перенесённые legacy строки ведут к D2/D3 IDs, aliases не добавляются |
| S1-03 /1.2-3 | B1/B2/B5: exact part/config/object, dirty сосед, отсутствие скрытой записи; L2 exact referenced configs | D2-CONFIG /2.5: произвольные multi-config/multi-body мутации и семьи |
| S1-04 /1.2-3,4 | B3/L2: уже поддержанные resolved repeated/nested instance paths и config membership | D2-LOADREF/D2-LARGE /2.6: suppressed/lightweight/SpeedPak/assembly-cut и 1000+ |
| S1-05 /1.2-4 | B3/B2: полный supported object/body scope, rename/stale/deleted/recreated/foreign refs | D2-GEOMETRY/D2-LOADREF /2.1,2.6: произвольная topology/поверхности/многотельность и остальные состояния |
| S1-06 /1.2-5 | B1/B3: units/SI и уже поддержанные explicit rigid frames; полное без скрытого смещения | D2-FRAMES /2.1,2.6: native named frames и прочие измерения/системы координат |
| S1-07 /1.2-6 | B4/B2: реальные rebuild/postcondition ошибки supported fixture, исходная ошибка не маскируется | D2-GEOMETRY /2.1: произвольные дефектные/импортированные topology; каждый новый scope требует своей диагностики |
| S1-08 /1.3-1 | Все блоки: ручное изменение, stale/foreign/config mismatch до записи; revision не только stamp | D2-CONFIG/D2-GEOMETRY /2: широкая модель при появлении её поддержки |
| S1-09 /1.3-5 | B1/B2/B4/L2/L3: durable checkpoint, exact owned/scalar restore, unchanged neighbours/UI/settings | D2-SHEET/D2-GEOMETRY /2: scoped restoration новых инженерных операций; generic Undo не обещается |
| S1-10 /1.3-3,4 | B4/B5: timeout/late result/replay/conflict/queued cancel/restart→unknown на installed wheel | Нет переноса гарантий; расширенные CAD-процессы получают те же guards в своих стадиях |
| S1-11 /1.3-6 | B4: persistent holds/reconnect/no bypass/exact reconciliation | Нет переноса гарантий; неизвестное не success и не повторяется |
| S1-12 /1.4-1 | B2: полный supported simple impact preview и delete exact own leaf; incomplete/dependent graph отказ | D2-DELETION /2.1,2.5: произвольные dependencies/equations/configurations/annotations/external/incoming refs |
| S1-13 /1.4-2 | B2: finite driving length, фактическое значение/units/rebuild/readback/known restore; unsupported controls rejected | D2-DIMENSIONS /2.1,2.4,2.5: signed/angle/tolerance/read-only/linked/equation semantics |
| S1-14 /1.4-3 | B1/B2/B5: русские имена/native readback/PID независим от имени | D2-LIBRARY /2.6: русские имена экземпляров при сохранении filenames/SKU/стандартов |
| S1-15 /1.4-5 | L2/L3/B5: finite open, first part save, accepted clean close и existing-path Save3; dirty сосед | D2-CLOSE/D2-DOCUMENTS /2: dirty-owned/retained-reference/data unloading; first save assembly/drawing/ref cases |
| S1-16 /1.4-5 | B3/B5: публичные supported mass/bounds/distance/units/frame, selection restore | D2-FRAMES/D2-LOADREF/D2-LARGE /2: остальные assemblies/modes/native named frames/scale |
| S1-17 /1.4-5,1.2-6 | B1…B5/L2/L3: минимальная базовая миграция и явный статус всех31 legacy пунктов | D2-DOCUMENTS/D2-GEOMETRY/D2-CONFIG/D2-DIMENSIONS/D2-DELETION /2: остальные реализации таблицы ниже |
| S1-18 /1.5-1,2 | B4/B5: end-to-end/queue/supported prepare/native/postcondition/restore/logging, actual late result отдельно | D2-DIAGNOSTICS /2: полный COM census/grouping/performance, не скрытые synthetic timings |
| S1-19 /1.5-3 | B4: bounded private store, enabled/disabled/error isolation/privacy; без второго STA/лишнего COM | Dev69 scoped proof остаётся историей; расширенная overhead выборка D2-DIAGNOSTICS /2 |
| S1-20 /1.5-4 | B4: timings filters/count/median/p95/малые выборки/current actual outcomes; installed schema | D2-DIAGNOSTICS /2: workload grouping и широкий performance dashboard |
| S1-21 /1.4-4 | B4/B5: фиксировать фактическую длительность chain и устранить известные мешающие повторы без ослабления ревизии | D2-DIAGNOSTICS /2: общая performance-приёмка каждого scope/COM counter/1000+; dev49/dev55 история |
| S1-22 /gate5,6 | B5: same-wheel installed/native/public/cleanup/current manifest, SolidWorks2023 | Старый тотальный N0–N6 scope распределён между конечными блоками и D2/D3 задачами, не объявлен пройденным |

## Все 31 legacy пункта: видимая миграция

Имена здесь — исходный инвентарь, не v2 aliases. Реализованная замена обязана
иметь точный контракт; отложенная строка остаётся отложенной в MIGRATION_V2.

| Legacy группа/пункты | Обязательная замена/проверка | Видимый широкий остаток |
| --- | --- | --- |
| get_status, new_part, list_documents, activate_document, open_part, save_part, close_part, new_assembly, open_assembly, save_assembly | B1/B3/L2/L3/B5: новая part, чтения, explicit lifecycle activation, resolved open, first part save/Save3, clean close | D2-DOCUMENTS: standalone arbitrary activation, new assembly/drawing и first save с refs; D2-CLOSE: dirty-owned/ref-retained close |
| list_components, list_bodies, list_faces, list_edges, read_sketch, list_features | B3: уже поддержанные part/resolved reads и membership | D2-LOADREF/D2-GEOMETRY/D2-LARGE: остальные состояния/topology/scale |
| add_sketch, add_plane, add_box, add_extruded_profile, add_extruded_profile_on_plane, extrude_sketch | B1: simple rectangular 2D profile/box, explicit существующая native plane, blind extrusion | D2-GEOMETRY: самостоятельное создание/изменение auxiliary planes, arbitrary profiles и остальные end conditions |
| list_dimensions, set_dimension, delete_feature, suppress_feature, rebuild | B2/B4: driving length/readback/finite own graph deletion/suppression/rebuild | D2-DIMENSIONS/D2-DELETION/D2-CONFIG: полный прежний ассортимент semantics/graphs |
| get_mass_properties, get_bounding_box, get_assembly_bounding_box, measure_distance | B3: уже поддержанные public part/instance/aggregate measurements | D2-FRAMES/D2-LOADREF/D2-LARGE: новые frames/modes/масштаб |
| Новые v2: feature_rename, jobs/holds/reconciliation, diagnostics_get_timings | B2/B4/B5: гарантии и русские имена/диагностика штатной цепочки | D2-DIAGNOSTICS: расширенная эксплуатационная статистика; гарантии не переносятся |

Остальные61 legacy пункта уже относятся к инженерным стадиям2/3 в MIGRATION_V2.
Таблица не добавляет неподтверждённые tools в tools/list.

## Перенесённые и инженерные задачи: ни одна не passed этим пересмотром

| ID | Целевая стадия / результат | Конечная приёмка |
| --- | --- | --- |
| D2-DOCUMENTS | 2: новые пустые assembly/drawing; first save типов с refs; самостоятельный explicit activation | По одному native/public lifecycle каждого типа, identity/path mapping, first-save no-overwrite, active-after и unchanged referenced/dirty baseline |
| D2-CLOSE | 2: dirty-owned, retained-reference close и явная выгрузка данных | Native/public каждый объявленный режим; закрытый UI не выдаётся за выгруженные данные, no quit/no чужие collateral, disk/UI/refs postconditions |
| D2-LOADREF | 2.6: lightweight/suppressed/SpeedPak/virtual/assembly-cut и part external refs | Конечный inventory режимов, exact native handles/config/graph и отказ неподдержанного; targeted resolve без незаявленных эффектов |
| D2-CONFIG | 2.5: multi-config/multi-body mutation, families/equations/свойства/материалы | Exact целевые config/body; другая config/body неизменна; native computed/readback/rebuild и stale/restore |
| D2-DIMENSIONS | 2.1/2.4/2.5: signed/angle/tolerance/linked/equation controls | По одному positive/negative native случаю каждого заявленного типа, знак/допуски/readback; запрещённая запись не маскируется |
| D2-DELETION | 2.1/2.5: произвольный полный dependency graph delete | Native preview/execute с equations/config/annotations/external/incoming refs, stale refusal, exact retired/survivor sets и scoped restore |
| D2-FRAMES | 2.1/2.6: native named frames и новые measurement frames | Translated/rotated native fixtures, exact membership/units/witnesses, no implicit placement, selection restore |
| D2-DIAGNOSTICS | 2: workload grouping/full COM coverage и широкая performance-приёмка | Сопоставимый before/after на конечных fixtures, counters/интервалы/выборка; unchanged full revision; без CAD ради статистики |
| D2-GEOMETRY | 2.1: auxiliary planes/arbitrary profiles; holes/threads/fillets/patterns/loft/sweep/3D/surfaces/boolean/imported repair/tree reorder | По законченной инженерной цепочке, полный supported BREP/refs/parameters, native/public positive/stale/failure/restore; исторический scope не generic support |
| D2-SHEET | 2.2: листовой металл, пользовательский K, разгрузки/углы/развёртки | Native геометрия folded/flat, exact K/radius/thickness и repeatable bend; DXF зависит от D-DEFER-IMPORT |
| D2-WELD | 2.3: профили/рамы/cut lists | Native профили/стыки/обрезки и native cut-list lengths/quantities/properties |
| D2-DRAW | 2.4: ЕСКД/ГОСТ и наши шаблоны, views/dimensions/tolerances/BOM | Native sheets/model links/config, размещение и readback; согласованные шаблоны и контрольный комплект документации |
| D2-LIBRARY | 2.6: стандартные элементы из утверждённых библиотек | Reused file/config/version/SKU; повторные экземпляры/BOM без копий, no silent ambiguous substitution, русские instance names |
| D2-LARGE | 2.6: 1000+ components, selective resolution и performance | Обзор реальной контрольной >1000 сборки без полного resolve; пять exact выбранных компонентов, refs/конфигурации и latency/COM отчёт |
| D2-PDM | 2.7: SOLIDWORKS PDM Professional get/version/check-out/check-in | Отдельное тестовое vault, права/версия/владение lock, конфликты и committed состояние; user vault не fixture |
| D2-DISTRIBUTION | 2: публичное имя и согласованный выпуск пакета | Fork artifact/manifest/licence/attribution и штатный CI; публикация отдельным финальным действием |
| D3-KINEMATICS | 3.1: движение механизмов и зазоры по траектории | Контрольный механизм, ограничения/sampled trajectory/clearance; явно ограниченная точность, no неподтверждённая continuous safety |
| D3-SIM | 3.3: статическая прочность сборок с контактами | Тестовая лицензия/fixture, loads/material/contact/mesh/results и сходимость по согласованному набору |
| D-DEFER-STL | Отложено, 3.2: STL/3MF, сетки/печать/реконструкция | Native geometry/units/frame/settings/no-overwrite и declared mesh quality; возврат в работу отдельным решением |
| D-DEFER-IMPORT | Отложено, 3.4: STEP/IGES/Parasolid/DXF import/export | Exact native destination/frame/settings/ownership/no-overwrite/cleanup; возврат в работу отдельным решением |

## Исторические scoped доказательства

| Wheel | Принятый scope / ссылка | Что не следует из результата |
| --- | --- | --- |
| dev41/dev49 | [Русская простая part/box](PART_CREATION.md), [rectangular sketch dimensions](SKETCHES.md) | Нет first save или итогового S1-B5 |
| dev69 | [Bounded timings](DIAGNOSTICS_TIMINGS_ACCEPTANCE.md), metadata49/17, native20 reads/internal4 basic | Нет полного COM census/широкого performance или current wheel proof |
| dev71/dev72 | [Part mass](MASS_MEASUREMENT_ACCEPTANCE.md)22/6, [explicit rigid bounds](BOUNDS_MEASUREMENTS_ACCEPTANCE.md)14/6 | Нет arbitrary frames/всех assemblies |
| dev73/dev74 | [Resolved component/body](COMPONENT_READS_ACCEPTANCE.md)15/6; [normal face/edge topology](COMPONENT_TOPOLOGY_ACCEPTANCE.md)21/8 | Нет lightweight/SpeedPak/suppressed/assembly-cut всех режимов |
| dev75–dev79 | [Pair distance](COMPONENT_DISTANCE_ACCEPTANCE.md)13/6; [point](COMPONENT_POINT_DISTANCE_ACCEPTANCE.md)19/6; [axis](COMPONENT_AXIS_DISTANCE_ACCEPTANCE.md)18/6; [aggregate pair](COMPONENT_AGGREGATE_DISTANCE_ACCEPTANCE.md)19/6; [aggregate probes](COMPONENT_AGGREGATE_PROBES_ACCEPTANCE.md)24/8 | Нет native named frames/1000+ или нового same-wheel покрытия |
| dev82 | [Current-path Save3](NATIVE_DOCUMENT_SAVE_ACCEPTANCE.md): part/assembly/drawing internal10/public5, metadata67/19 | Не first save; dirty referenced child не был сохранён вместе с родителем |
| dev85 | [Clean native close](NATIVE_DOCUMENT_CLOSE_ACCEPTANCE.md): internal12/public10, metadata69/20, explicit hidden retirement, dirty сосед, survivor activation/empty baseline | Не dirty-owned/ref-retained close/data unload и не итоговый lifecycle |
| dev87 | [Bounded native open](NATIVE_DOCUMENT_OPEN_ACCEPTANCE.md): internal13/public11, metadata71/21, new/borrowed resolved refs и CWD/baseline восстановлены | Не first save, новые load/reference modes или итоговый same-wheel B5 |
| dev67/dev68 | [Edge flange](SHEET_EDGE_FLANGE_ACCEPTANCE.md)8/7; [U flat/fold](SHEET_FLANGE_FLAT_ACCEPTANCE.md)9/10 | Scoped стадия2, не переход/не завершение стадии1 |
| Legacy pilot | [20/20 и безопасная own очистка](LEGACY_CAD_BASELINE.md) | Остальные303 not_run; не заменяет v2 installed/native/public |

Старые N0–N6 — историческая группировка тестов, не открытый бесконечный gate.
N0/current installed покрывается S1-B5; supported N1/N2 — B1/B3; N3/N5 — B2/B4;
N4 — B4; конечный native-file N6 — L2/L3/B5. Широкие случаи каждой группы ведут
к видимым задачам D2/D3 выше. Ни один перенос не закрывает historical unknown.

## Порядок исполнения и закрытия

L2 закрыт dev87; далее L3 → остатки B1–B4 → S1-B5. По каждой строке
записывать actual supported cases/result/limits и wheel identity. Подробные
native отказы — internal; public MCP — контракт/журнал/user chain. Не повторять
те же физические случаи без причины. Общие fixture-сценарии покрывают несколько
строк; ordinary docs не требуют native rerun. Связанные pure после правок,
полный pure перед итоговым wheel и после обоснованной общей регрессии.

Контрольная точка после 3–5 законченных блоков либо конца дня; local commits
и один пакетный push/PR со штатным CI, [процесс](GIT_WORKFLOW.md).
Независимые файлы можно параллелить; SW/COM/native/integration один владелец.
Стадия1 закрывается по семи блокам, без требования выполнить перенесённые D2/D3.
