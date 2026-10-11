# Конечная матрица незакрытых требований стадии 1

Dev85: clean native close принят:4673 pure перед wheel; final пакет4677/323 CAD deselected (60,07с). Installed metadata69/20,
internal12/public MCP10 accepted=true на одном точном wheel. Полный retirement
assembly+explicit hidden collateral, part/drawing, dirty сосед, replay/stale,
explicit survivor activation и empty/free baseline подтверждены.
[Контракт](NATIVE_DOCUMENT_CLOSE.md), [приёмка](NATIVE_DOCUMENT_CLOSE_ACCEPTANCE.md).
First save/open, dirty-owned/retained-reference close и общий N6 остаются;
стадия1 открыта,20 из22 требований по-прежнему открыты полностью/частично.
Прежние scoped результаты привязаны к своим wheel; legacy20/20 отдельно.


Dev82: сохранение существующего native-файла детали/сборки/чертежа принято:
4455 pure/323 CAD deselected перед wheel (55,56 с); после изменения общего
verifier и добавления69 pure-регрессий итоговый пакет4524 passed/323 deselected
(59,92 с). Installed metadata67/19, internal native10/public MCP5 accepted=true
на одном точном wheel. Перечитывание трёх типов файлов, сохранность dirty
referenced child, replay/stale и exact-owned cleanup/baseline подтверждены.
[Контракт](NATIVE_DOCUMENT_SAVE.md), [приёмка](NATIVE_DOCUMENT_SAVE_ACCEPTANCE.md).
Первое сохранение и публичные open/close остаются обязательными S1-15;
[проект следующего блока](NATIVE_DOCUMENT_LIFECYCLE_DESIGN.md).
Стадия1 открыта;20 из22 требований остаются открытыми полностью/частично.
Legacy20/20 — отдельный source-пилот, не приёмка v2.

Исторический dev79: расстояния от полного solid-агрегата part/subassembly до точки
и бесконечной оси приняты:4409 pure/323 CAD deselected (57,25 с), installed
metadata65/18, internal native24/public MCP8 accepted=true на одном wheel.
Exact4-owned cleanup, пустой/free baseline и non-STL preferences подтверждены.
Hidden cylinder3/6/0 мм для точки и2/0 мм для оси, explicit rigid frame,
native configuration replacement, multibody3/2 и replay проверены.
[Контракт](COMPONENT_AGGREGATE_PROBES.md), [точная приёмка](COMPONENT_AGGREGATE_PROBES_ACCEPTANCE.md).
Native named frames, остальные состояния/измерения сборок, масштаб1000+
и общий N0–N6 остаются. Следующий обязательный блок — native open/save/close
S1-15. Стадия1 открыта, расширения2 отложены; legacy20/20 учитывается отдельно.

Исторический dev78: расстояние между полными solid-агрегатами part/subassembly принято:
4365 pure/323 CAD deselected (54,78с), installed metadata63/18,
internal native19/public MCP6 accepted=true на одном wheel. Exact4-owned
cleanup, пустой/free baseline и non-STL preferences подтверждены. Полный
leaf census/все пары, hidden cylinder minimum84 мм, shared descendant0,
explicit rigid frame, native смена конфигурации/rename/move проверены.
[Контракт](COMPONENT_AGGREGATE_DISTANCE.md), [точная приёмка](COMPONENT_AGGREGATE_DISTANCE_ACCEPTANCE.md).
На момент dev78 point/axis distance агрегатов, native named frames и общий N0–N6 оставались;
S1-06/S1-16 и стадия1 открыты. Legacy-пилот учитывается отдельно.


Исторический dev77: расстояние resolved экземпляра детали до бесконечной оси принято:
4335 pure/323 CAD deselected (54,63с), installed metadata62/18,
internal native18/public MCP6 accepted=true на одном wheel; exact4-owned
cleanup, baseline и non-STL preferences подтверждены. Exact directional
supports + memory-only wire, hidden/rotated/nested instances, oblique axis,
explicit rigid frame, far origin/reversed direction, cylinder surface gap/tangency.
[Контракт](COMPONENT_AXIS_DISTANCE.md), [точная приёмка](COMPONENT_AXIS_DISTANCE_ACCEPTANCE.md).
На момент dev77 aggregate subassembly, named native frames и общий N0–N6 оставались;
S1-06/S1-16 и стадия1 открыты, расширения2 отложены. Старые приёмки ниже
относятся к их wheel и не засчитываются в итоговый gate текущего кандидата.

Исторический dev76: point boundary distance/native location для resolved part instance принят:
4287 pure/323 CAD deselected (53,93с), installed metadata61/18,
internal native19/public MCP6 accepted=true на одном wheel; exact4-owned
cleanup, baseline и non-STL preferences подтверждены. Hidden rotated
inside/outside/boundary, explicit frame/trimmed corner, nested/multibody,
solid cylinder и hollow cavity/material, old replaced body/face rejection.
[Контракт](COMPONENT_POINT_DISTANCE.md), [точная приёмка](COMPONENT_POINT_DISTANCE_ACCEPTANCE.md).
На момент dev76 axis distance, aggregate subassembly targets, named native frames и общий
N0–N6 остаются; стадия1 открыта, расширения2 отложены.

Dev75: расстояние между двумя resolved экземплярами деталей принято:
4236 pure/323 CAD deselected (53,88с), installed metadata60/18,
internal native13/public MCP6 accepted=true на одном wheel; exact-owned cleanup
и baseline подтверждены. Hidden rotated/multibody15 мм, nested70 мм,
curved overlap/tangent0, native move14 мм, cylinder gap24 мм вместо axis36 мм.
[Контракт](COMPONENT_DISTANCE.md), [точная приёмка](COMPONENT_DISTANCE_ACCEPTANCE.md).
На момент dev75 S1-16/S1-06 частично: point/axis distance, агрегат подсборки, native named
frames и общий N0–N6 остаются; стадии1/2 не объявлены завершёнными.

Срез: 11.10.2026. Основание — обновлённые PLAN.md и PLAN_STATUS_AUDIT.md,
исходники, связанные тесты и отчёты точных wheel. Матрица фиксирует конечный
перечень требований, а не приёмку. Стадия 1 остаётся открытой. Новые расширения
2.1/2.2 не начинать до её завершения. Обмен файлами 3.4 и STL3.2 отложены.

Отбортовка dev67 **принята**: internal8/public7 accepted=true на одном wheel;
см. [точную приёмку](SHEET_EDGE_FLANGE_ACCEPTANCE.md). Аудит, где dev67 ещё
выполнялся, является историческим срезом. Dev68 содержит начатую ранее
U-развёртку:3997 pure/323 CAD deselected, metadata48/17,
internal9/public10 accepted=true на одном wheel; own fixtures закрыты,
baseline восстановлен. [Приёмка](SHEET_FLANGE_FLAT_ACCEPTANCE.md).
Его выполнение не означает переход к стадии 2.

Dev73: scoped адресация resolved экземпляров/normal solid-surface тел принята:
4175 pure/323 CAD deselected, metadata56/18, internal15/public6 на одном wheel,
own cleanup/baseline. [Свидетельство](COMPONENT_READS_ACCEPTANCE.md).
S1-04/S1-05/S1-06 остаются частично открытыми; требования не сокращены.

Dev74: normal instance face/edge context принят:4210 pure/323 CAD deselected,
metadata59/18, internal21/public8 на одном wheel, own cleanup/baseline.
[Свидетельство](COMPONENT_TOPOLOGY_ACCEPTANCE.md). Native rename/delete/recreate
и hidden/curved topology доказаны; S1-04/05/06 остаются открытыми для полного scope.

## Правила закрытия

- Каждая строка имеет один конечный результат и доказательство. Код/pure,
  установленный пакет/MCP и фактическая CAD-операция учитываются раздельно.
- Все обязательные итоговые installed/native-сценарии относятся к **одному
  итоговому wheel**: версия, полный Git SHA, digest и SHA256. Старые приёмки —
  основания для выбора проверок, а не результаты нового кандидата.
- Не повторять всю историческую CAD-матрицу. Собрать общие fixture-сценарии,
  покрывающие несколько требований; подробные отказы — внутри native-стенда,
  public MCP — контракт, журнал, пользовательская цепочка и request_id.
- Skipped, ещё running, cleanup после unknown и metadata-only не считаются
  CAD-успехом. Unknown не повторять; штатная очистка собственных terminal
  документов разрешена пользователем, чужие документы сохраняются.
- Отказ unsupported подтверждает защиту, но не закрывает требование поддержки
  нескольких конфигураций, тел, component paths или координатных систем.
- Изменение области требований требует решения пользователя. Эта матрица
  не переносит незакрытые требования в поздние стадии ради отметки «готово».

## Остатки реализации и проверки

Все строки ниже открыты, кроме S1-02 и S1-19 в явно указанной области текущего каталога/диагностики. Это не закрывает общую миграцию S1-17 или итоговую приёмку S1-22.
Номера пунктов после дроби соответствуют порядку checkbox в разделе PLAN.

| ID / PLAN | Что осталось; конечный результат | Чем проверяется | Что блокирует закрытие |
| --- | --- | --- | --- |
| S1-01 /1.1-5 | Воспроизводимый итоговый wheel, актуальный CI форка, собственное имя пакета и согласованный выпуск | Pure/build/installed metadata локально; затем один цельный PR/обязательный CI. Манифест выпуска с точным wheel и native-отчётами | Общий native-gate не принят; нет актуального CI этого пакета и выбранного имени публичного пакета. Публикация — отдельный финальный шаг |
| S1-02 /1.2-1,1.4-5 | Актуальная миграция всех legacy-инструментов: реализованная замена, изменённый контракт или явно отложенный пункт; guide/каталог согласованы | Статическая сверка регистрации с installed tools/list; проверка ссылок всех92 legacy-строк, counts и новых инструментов | **Готово для каталога dev82:** статическая сверка92 legacy-строк/67 реализованных tools, все замены/guide согласованы с installed67/19. Общая native-миграция — S1-17, финальный каталог — S1-22 |
| S1-03 /1.2-3; gate1 | Явная цель в двух документах, нескольких конфигурациях и многотельной детали; нужная операция изменяет только выбранный объект | Native N1: два документа, два тела и две конфигурации; проверка full snapshots/PID до/после и отсутствия скрытой активации. Public запрос с явным контекстом | Нет общей принятой multi-config/multi-body мутации на итоговом wheel; существующие инженерные scopes ограничены |
| S1-04 /1.2-3,1.2-4 | Component path различает два экземпляра одного файла и их конфигурации; геометрия относится к точному экземпляру/телу | Native N2: малая собственная сборка с повторным экземпляром; foreign instance/stale/deleted refs, membership и transforms | Частично принято dev73: repeated-file instances, разные referenced configs, nested parent paths, transforms и normal solid/surface тела, internal15/public6. Dev74 принял normal component face/edge context, hidden/curved BREP и native deleted/recreated refs21/8. Остались suppressed/lightweight/SpeedPak/assembly-cut состояния и общий N2/final gate. Mates/1000+ —2.6 |
| S1-05 /1.2-4 | Полный native scope устойчивых ссылок solid/surface и multi-body; ссылки после rename сохраняются, после удаления/замены отвергаются | Native N1/N2: persistent-reference roundtrip, полный body membership, старый токен/чужая цель, suppressed/deleted/recreated объект | Dev73 принял scoped assembly body roundtrip/foreign membership, native rename component reference и changed-config отказ; dev3 — исторический part-read scope. Dev74 принял normal face/edge roundtrip, rename и native deleted/recreated instance отказы, включая solid/surface/cylinder. Suppressed/прочие состояния, изменение/замена внутренней topology детали и полный current final scope ещё открыты |
| S1-06 /1.2-5 | Мм/градусы/кг, SI, явные плоскости и произвольная система координат без скрытого смещения/масштаба | Pure преобразования/нечисловые значения; Native N1/N2 смещённая и повёрнутая frame, аналитические координаты/масса/расстояния | Dev72 part bounds в явно переданном rotated/shifted rigid frame приняты (internal14/public6). Dev73 принял local body coordinates и native root assembly transforms (включая вложенность/90° rotation/shift). Dev74 принял component-local face/edge summaries и closed curves. Dev75 component distance с двумя root assembly точками принят13/6, включая rotated/nested transforms. Dev76 point distance/location с root и explicit rigid frame принят19/6. Dev77 infinite-axis distance/root и explicit rigid frame принят18/6; exact support span и witnesses проверены. Dev78 aggregate pair distance/root и explicit rigid frame принят19/6. Dev79 aggregate point/axis/root/explicit rigid frame принят24/8. Общая геометрия, component/native named measurement frames и результаты остальных измерений в произвольных frames не приняты. Импорт к этому gate не добавляется |
| S1-07 /1.2-6,gate3 | Отличать исходный rebuild-дефект от нового; rebuild setter/readback и постусловия не маскируют ошибку | Native N3: реально дефектная fixture плюс новая ошибка реального rebuild; исходная ошибка сохраняется, новый дефект блокирует success | Injected Python failure не доказывает реальные CAD rebuild-ошибки; итоговая матрица не выполнена |
| S1-08 /1.3-1,gate2 | Ручное изменение, неправильная ревизия, старый/чужой объект и смена конфигурации отвергаются до первой записи | Pure adversarial snapshots; Native N1/N3 ручные изменения имени/размера/геометрии без доверия одному stamp; проверка checkpoint/записи | Приняты отдельные stale-сценарии, общей матрицы ручных изменений выпускаемого scope нет |
| S1-09 /1.3-5,gate3 | Durable checkpoint и безопасное восстановление новой операции и существующего параметра; имена/выделение/view/настройки сохранены | Native N3 создание + scalar change с известным отказом; точные scope/PID и полные before/after. Unknown при неподтверждённом возврате | Исторические block receipts есть; совокупная проверка итогового кандидата отсутствует. Generic Undo не принят и не подменяет scoped restore |
| S1-10 /1.3-3,1.3-4,gate4 | Поздний результат после timeout, queued-only cancel, request conflict/replay без дубля; installed restart unfinished→unknown без replay | Installed N4: отдельный процесс stdio, timeout0/job_get/replay, queued cancel и restart. Native выполнение одной своей операции с поздним завершением; авария только собственного тестового процесса | Pure lifecycle и ограниченный native replay приняты; установленная общая restart/native-матрица не завершена |
| S1-11 /1.3-6 | Holds переживают restart/reconnect, не обходятся новой эпохой/другим документным ID; exact reconciliation без ложного success | Installed/native N4: uncertain собственного задания, restart, отказ записи в held цель, доступная другая цель; closing proof согласования | Нет общей installed/native приёмки restart/reconciliation. Нельзя убивать исполняющийся COM или закрывать чужую модель |
| S1-12 /1.4-1 | Полный impact preview удаления и execute ровно подтверждённого набора: дерево, зависимости, equations/configurations/annotations/external/incoming refs | Pure graph/context completeness; Native N5 dependency fixture, preview read-only, stale before execute, postcondition и scoped restoration. Неполный inventory явно блокирует execute | Есть внутренние graph/context, но нет полного preview и публичного execute; инвентари и native effect/restoration неполны |
| S1-13 /1.4-2 | Реальное значение, знак, единица, допуск и driving/read-only/link semantics размеров; ограниченный повтор не скрывает ошибку | Pure типы/значения/допуски; Native N3/N6 поддерживаемые distance/angle/signed/tolerance случаи, запрещённые controls, фактический readback и restore | Отдельные размеры приняты, общей размерной области и знаков/допусков нет |
| S1-14 /1.4-3 | Единая русская политика имён создаваемых узлов/компонентов/размеров; readback ошибки видимы, PID не зависит от имени | Pure defaults/catalog; native/public N1/N2/N3 rename/create и exact readback. Library filenames/SKU/standards не локализуются | Нужна общая выпускаемая область. Библиотечные сборки2.6 не добавляются как предварительное условие этого правила |
| S1-15 /1.4-5 | Базовые native документы: явные open/save/close, безопасное владение, без потери несохранённых пользовательских изменений | Native N6 собственные временные native-файлы, save/readback/open/close точной цели; public lifecycle; untouched исходный документ | **Частично:** current-path Save3 детали/сборки/чертежа принят dev82, internal10/public5 и независимый disk/native readback, dirty child сохранён. [Приёмка](NATIVE_DOCUMENT_SAVE_ACCEPTANCE.md). Clean public close принят dev85 (internal12/public10), [приёмка](NATIVE_DOCUMENT_CLOSE_ACCEPTANCE.md). Первое сохранение/open, dirty-owned/retained-reference close остаются, проект L1–L3 — [lifecycle](NATIVE_DOCUMENT_LIFECYCLE_DESIGN.md); общий N6 не закрыт |
| S1-16 /1.4-5 | Публичные измерения массы, габаритов и расстояний с явными объектами/units/frame, актуальными overrides и сохранением selection | Pure существующего mass backend + новый фасад; native/public N1/N2/N6 аналитические тела/выбор тел/overrides/selection restore | Публичная масса детали dev71 принята в ограниченном scope: internal22/public6 accepted, metadata51/18, own cleanup/baseline. Габариты детали dev72 приняты:internal14/public6,metadata52/18, own cleanup/baseline. Dev75 distance между resolved part instances принят13/6,metadata60/18. Dev76 point boundary distance/native location принят19/6,metadata61/18. Dev77 infinite-axis distance принят18/6,metadata62/18. Dev78 complete aggregate pair distance принят19/6,metadata63/18. Dev79 aggregate point/axis distance принят24/8,metadata65/18. Остальные assemblies/component/native named frames и общий gate остаются; см. MASS_MEASUREMENT_ACCEPTANCE.md и BOUNDS_MEASUREMENTS_ACCEPTANCE.md |
| S1-17 /1.4-5,1.2-6 | Остальные базовые операции и rebuild имеют явную таблицу переноса и реальные реализации; ни одного неподтверждённого обещания каталога | Завершить S1-02: перечислить каждый базовый legacy-пункт с контрактом/проверкой/блокером; native N6 и профильные N1–N5 | Нельзя объявить миграцию закрытой по последним CAD-фичам; неперенесённые базовые операции остаются открыты; граница зафиксирована пользователем11.10.2026; обязательный базовый инвентарь ниже не завершён, общий кандидат не принят |
| S1-18 /1.5-1,1.5-2 | Монотонные end-to-end/queue/prepare/COM/rebuild/postcondition/restore/logging интервалы; timeout отдельно от завершения, polling отдельно от CAD | Pure nested interval и lifecycle; установленный MCP diagnostics на фактической операции N3/N6; допустимые неразделимые интервалы явно обозначены | В исходниках подключены traces к JobRunner/MutationCoordinator и MCP-фасаду;34 новых timing pure passed, связанные existing проверки прошли. Installed49/17, stdio, native20 reads/internal4 basic приняты dev69. Selected COM/positive phases доказаны; grouping геометрии, полный COM census и native failure/restart timing остаются |
| S1-19 /1.5-3 | Настройка, ограничение объёма/retention, изоляция ошибки диагностики, приватность; без дополнительных COM/второго STA | Pure retention/ошибки/allowlist без payload/paths/names; installed enabled/disabled/report; native N6 сопоставимый замер накладных расходов | **Готово в области dev69:** bounded private store/CLI и изоляция ошибок;34 новых timing pure passed, installed/stdin modes/native20 reads/internal4 basic accepted. Small-sample overhead измерен; общий CAD performance — S1-21. Обязательный job journal отдельный; см. DIAGNOSTICS_TIMINGS_ACCEPTANCE.md |
| S1-20 /1.5-4 | Один diagnostics_get_timings: период/инструмент, count/median/p95/медленные этапы, отдельные исходы/сборки/сценарии | Pure статистика/фильтры/малые выборки; installed outputSchema и public MCP; реальные записи из штатного native-прогона | diagnostics_get_timings реализован в исходниках;pure schema/filter/count/median/p95 проверены. Installed49/17 и native-записи20 reads/internal4 basic приняты. Workload-сценарии пока unclassified_v1; общий приёмочный wheel N0–N6 ещё нужен. См. DIAGNOSTICS_TIMINGS_ACCEPTANCE.md |
| S1-21 /1.4-4,gate7 | Время и явные COM-dispatches по чтению/ревизии; устранить конкретные повторы внутри одного чтения без ослабления двух границ | Native N1/N6 before/after на одной fixture; counters и неизменная полная ревизия, closing identities/geometry, условия/выборка. Учесть историческую dev55 оптимизацию | Исторические узкие замеры не являются performance-приёмкой всей выпускаемой области; полный заявленный scope не измерен |
| S1-22 /gate5,gate6 | Совокупный installed/stdio/catalog/native gate на SolidWorks2023; точный отчёт пропусков/отказов/unknown и исходное состояние восстановлены | N0 metadata exact tools/schema/build; N1–N6 native/public по покрытию; финальный манифест cases→строки этой матрицы | Нет итогового кандидата и принятых обязательных N1–N6;65/18 metadata и scoped aggregate point/axis native24/public8 dev79 не заменяют совокупную CAD-приёмку |

## Конечный набор групп приёмки

Ниже группы с конкретными моделями/состояниями. Их сценарии детализируются при
реализации строк, новые product-возможности стадии2 в эти группы не добавляются.
Итоговый манифест должен перечислить отдельные случаи и их outcomes.

| Группа | Собственные fixtures и назначение | Строки |
| --- | --- | --- |
| N0 | Точный installed wheel; version/Git/digest/tools/list/outputSchema/stdio; без CAD | S1-01,02,20,22 |
| N1 | Две открытые детали; несколько конфигураций; два solid и surface; renamed/deleted/replaced refs; явная повёрнутая/смещённая frame | S1-03,05,06,08,14,16,21,22 |
| N2 | Малая сборка, два экземпляра одного собственного файла, явные instance paths/configurations/transforms; чужой/старый объект | S1-04,05,06,14,16,22 |
| N3 | Существующий параметр и новая операция; исходный/новый реальный rebuild-дефект; stale, checkpoint, successful scoped restore и unproved/hold | S1-07,08,09,13,14,18,22 |
| N4 | Собственный stdio-процесс/журнал; late completion/replay/conflict/cancel/restart/unknown, persistent document/application holds и reconciliation | S1-10,11,22 |
| N5 | Полный граф удаления с dependencies/equations/configurations/annotations/outgoing/incoming refs; preview/execute/stale/postcondition/restoration | S1-12,22 |
| N6 | Собственные native files для open/save/close/rebuild; подписанные размеры/допуски, публичные mass/bounds/distance; диагностика enabled/disabled | S1-13,15,16,17,18,19,20,21,22 |

## Зафиксированная область базовой миграции

Пользователь выбрал11.10.2026: **документы, адресация, эскизы/плоскости,
базовое выдавливание, размеры, удаление/подавление, измерения и диагностика**.
Новые инженерные операции — стадия2. Все gates безопасности/native сохраняются.
Это решение устраняет старую неоднозначность «1.4/2.1»; оно не сокращает
конфигурации/тела/component paths, ревизии, postconditions или восстановление.

Фиксированный базовый legacy-инвентарь S1-17; имена ниже не являются v2-алиасами:

| Группа | Legacy-пункты, для которых нужна явная реализованная замена/контракт | Остаток |
| --- | --- | --- |
| Документы | get_status, new_part, list_documents, activate_document, open_part, save_part, close_part, new_assembly, open_assembly, save_assembly | Чтения/новая деталь есть частично; прочие жизненные операции, явный контекст и проверка текущего кандидата открыты. Создание сборки здесь — только пустой native документ; компоненты/mates/библиотеки —2.6 |
| Адресация и геометрические чтения | list_components, list_bodies, list_faces, list_edges, read_sketch, list_features | Part-чтения частично; dev73 scoped resolved component paths/configurations/transforms и normal solid/surface body context приняты15/6. Normal component face/edge scope dev74 принят21/8; остальные состояния и общий native scope открыты |
| Базовые эскизы/плоскости/выдавливание | add_sketch, add_plane, add_box, add_extruded_profile, add_extruded_profile_on_plane, extrude_sketch | Собственный прямоугольный эскиз/основание приняты в ограниченных исторических цепочках; самостоятельные операции и явная область базовых плоских профилей ещё не завершены. 3D/spline/sweep/loft сюда не включаются |
| Размеры/элементы/перестроение | list_dimensions, set_dimension, delete_feature, suppress_feature, rebuild | Размеры частично; знак/допуски/readback, полный delete preview/execute, suppression и общий rebuild/restore-gate открыты |
| Измерения | get_mass_properties, get_bounding_box, get_assembly_bounding_box, measure_distance | Публичный mass bridge детали dev71 принят (22/6); габариты детали dev72 приняты (14/6); distance/assembly/component frame и общий итоговый gate остаются |
| Новые v2 основы | feature_rename, durable jobs/holds/reconciliation, diagnostics_get_timings | Имена/jobs частично приняты; restart/holds/общий gate и диагностический фасад/native-проверка открыты |

Совокупная миграция этих31 legacy-пунктов и новых v2 основ закрывается только
реализациями и обязательными N0–N6. Остальные61 legacy-пункт распределены
по инженерным расширениям2 и отложенной3 в MIGRATION_V2; текущие ограниченные
замены инженерных операций сохраняются с точными историческими приёмками.
Ни одна ещё не реализованная функция не добавляется в tools/list.

## Порядок исполнения

Пункты1–3 выполнены в своей области: U dev68, инвентарь dev69/71,
диагностика dev69. В пункте4 приняты публичная масса детали dev71 и габариты
в явном rigid frame dev72; далее
закрывать native documents/остальные измерения/базовые операции и адресацию,
затем общие gates. [Свидетельство массы](MASS_MEASUREMENT_ACCEPTANCE.md).


1. Дождаться известного исхода текущего dev68-вызова; записать результат и
   terminal/cleanup. Не расширять U-scope ради следующей стадии.
2. S1-02: исправить сводную миграцию и guide, составить точный инвентарь S1-17.
   Это работа с документацией/каталогом, повторная CAD-приёмка не нужна.
3. Небольшой законченный блок S1-18–20: сборщик, bounded private store,
   diagnostics facade. Использовать реальные записи следующих штатных native
   проверок; не строить панель мониторинга и не запускать CAD ради статистики.
4. Завершать базовые реализации S1-15/16/17 и адресацию S1-03–06; затем
   S1-12/13 и конкретные обнаруженные defects S1-07–11. После небольших правок
   только связанные pure-тесты; итоговый pure перед wheel блока.
5. Свести покрытие N0–N6, выполнить недостающие installed/native cases на одном
   финальном кандидате; исторические отчёты не переобъявлять новыми.
6. S1-01/22: цельный пакет в форк через Git/API, обязательный CI/PR и отдельно
   согласованный выпуск. После доказанной приёмки обновить PLAN и перейти к2.

Работа — одним агентом. Связанные изменения и коммиты накапливаются локально;
push после каждой правки и запуск дополнительных агентов не предусмотрены.
