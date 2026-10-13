# S1-B3: конечная карта приёмки адресации и измерений

12.10.2026. Read-only аудит реализации и существующих стендов. **B3 открыт**:
этот документ задаёт конечный набор совместимости итогового установленного
wheel; native/MCP-вызовы и тесты при подготовке карты не запускались.
Основание: [план](../PLAN.md), [матрица](STAGE_1_REQUIREMENTS_MATRIX.md),
[пять условий B3](STAGE_1_BLOCK_ACCEPTANCE.md#s1-b3--адресация-и-измерения).
Исторический accepted конкретного wheel не переносится на итоговый кандидат.

## Поддержанный результат и границы

Пользователь получает актуальные ссылки документа, элемента, тела, грани,
ребра и размера; различает повторные экземпляры одного файла; получает
измерения с проверенными единицами, frame и исходными witnesses.

| Семейство реализованных tools | Заявленная область и обязательное различие |
| --- | --- |
| `document_list/get`, `feature_list/get`, `dimension_list/get`, `sketch_get` | Явная самостоятельная part и область конкретного чтения. Document metadata может описать существующую конфигурацию без её активации; геометрические чтения требуют активную конфигурацию. Feature/dimension snapshots не обещают произвольный CAD/add-in scope. Размеры возвращаются в mm/deg; sketch dimensions read-only. |
| `body_list`, `face_list`, `edge_list`, `geometry_get` | Normal solid/surface BREP в активной конфигурации part; persistent owner/membership и страницы. Body summary `GetBodyBox` приблизительный, не точный measurement bounds и не mutation BREP proof. |
| `component_list/get`, `component_body_list/get`, `component_face_list`, `component_edge_list`, `component_topology_get` | Малая полностью resolved root assembly; repeated/nested instances, referenced configurations, normal solid/surface и hidden. Body/face/edge координаты локальные `component_model`; total transform переводит в root assembly. Part IDs и instance IDs невзаимозаменяемы. |
| `measurement_prepare_mass/get_mass` | Все solid или одно явно выбранное solid-тело part, включая hidden; surfaces исключены, overrides запрещены. mm³/mm²/kg, center в model mm. Временное выделение защищается application checkpoint и восстанавливается. Масса сборки и custom mass frame не реализованы этим scope. |
| `measurement_get_bounds` | Native extrema normal solid/surface part; все или одно тело, фильтр типа. Model либо явно переданный правый rigid frame; нулевой extent плоской поверхности допустим. Не assembly bounds/минимальный OBB/native named frame. |
| Три `measurement_get_component_{distance,point_distance,axis_distance}` | Explicit resolved part instances, hidden solids включены, surfaces исключены. Pair — root metric/witnesses; point/axis допускают explicit rigid frame. Point — минимум до индивидуальных solid boundaries, axis — бесконечная прямая, zero не classifier interference. |
| Три `measurement_get_component_aggregate_{distance,point_distance,axis_distance}` | Part/subassembly, полный supported leaf/body census, включая hidden; surfaces/empty leaves проверяются, но не входят в solid минимум. Root либо explicit rigid frame, исходные nearest instance/body/face в соответствии с DTO. Никакой sampled/partial замены. |

Новые load/topology/frame/scale случаи остаются D2-LOADREF, D2-GEOMETRY,
D2-FRAMES, D2-LARGE; multi-config записи — D2-CONFIG. Численные budgets
реализации не являются доказательством работы со сборками 1000+.
Отражённый transform имеет контракт чтения, но исторический native mirrored
instance не принят; представительный B3 использует уже проверенные rigid
rotated/shifted экземпляры и не расширяет это обещание.

## Конечный manifest

Предлагается **13 именованных внутренних групп** ниже: фиксированные inputs и
assertions, а не сумма всех исторических native-наборов. Внутри каждой группы
полный необходимый inventory/closing snapshots сохраняются. Число физических
вызовов измеряется отдельно и не подменяется числом строк manifest.

Две последовательные fixture-сессии, один CAD-владелец. Part-профиль: два блока
20×10×5 мм с X-offset 0/40, поверхность 15×10 мм, цилиндр Ø12×30 мм; отдельный
dirty сосед 5×6×7 мм. Assembly-профиль переиспользует существующие helpers:
повторные part/config instances, две подсборки, вложенный hidden cylinder,
rotated/shifted placement. Создание fixtures — служебный setup, не приёмка новых
v2 инженерных операций. Все собственные новые имена русские.

| ID / условие | Конечная проверка и критерий |
| --- | --- |
| B3-I01 /N1 | `document_list/get` двух part; metadata обоих существующих configs; feature/dimension list→get в поддержанном профиле, `sketch_get` отдельно на одноконфигурационной прямоугольной пластине B1 того же wheel. Не требовать sketch API на multibody/surface fixture. mm/deg, owner и actual native значения совпадают; active document/config остаются прежними. Для unsupported встроенных feature/dimension rows допустим только объявленный `object_id=null`. |
| B3-I02 /N1 | Два solid + surface: body/face/edge list→get, одна полная face pagination с limit=2. У блока 6 faces/12 edges, суммарные area 700 мм² и edge length 140 мм; у surface 1 face/4 edges, 150 мм²/50 мм. Foreign body и inactive geometry config отвергаются. |
| B3-I03 /N2 | Repeated file: distinct instance IDs, два referenced configs с разными body rosters, nested parent path, independent total transform. Component/body/face/edge roundtrip подтверждает exact owner; передача body между instances/part/другим root отвергается. Чтение referenced config не переключает общий part document. |
| B3-I04 /N3 | Native rename собственного part feature и assembly instance: исходные feature/instance/face refs разрешаются к прежней canonical identity. Новая enumeration может вернуть native PID alias; текст имени не становится ключом и побайтовое равенство новых IDs не навязывается. B2 rename receipt можно переиспользовать только на том же wheel с полным evidence. |
| B3-I05 /N3 | Собственный cylinder instance удалить и вставить тот же файл заново: старый instance/face ID после обоих событий отвергается при свежем observation; новая ссылка принадлежит новой инкарнации. Это проверка адресации, не приёмка публичного delete/restore B2. |
| B3-I06 /N3 | Сменить referenced configuration только собственной fixture; старые component/body/face refs отвергаются, новые имеют exact новый roster. Старая конфигурационная part body reference также отвергается; чтение inactive config не делает hidden switch. |
| B3-I07 /N4 | Mass: all solids и explicit второй solid; объём 2000/1000 мм³, area 1400/700 мм², center X=30/50 мм. Масса сверяется с независимо наблюдаемой эффективной native density: V·density/10⁹ kg, без произвольной заданной плотности. Hidden solid включён, surface исключена; выбранное чужое UI-тело возвращается точно. |
| B3-I08 /N4 | Bounds: второй блок в shifted/rotated explicit frame; planar surface с нулевым extent; цилиндр в tilted frame. Независимые углы блока/поверхности и support круга дают expected extrema. Reflection frame, foreign body, stale observation отклоняются; approximate AABB corners не oracle. |
| B3-I09 /N4 | Part-instance pair distance на известном placement: 15 мм и nested 70 мм, closer surface исключена. Witnesses в root, metric, exact instances и полный solid census проверены независимо. |
| B3-I10 /N4 | Part-instance point/axis: explicit frame point-to-trimmed-corner √425 мм с local/root nearest; cylinder axis gap 2 мм и intersecting axis 0 мм. Native point location и original nearest face/body проверены; ось бесконечная и witnesses лежат на ней. |
| B3-I11 /N4 | Aggregate pair: part→subassembly 70 мм; repeated subassemblies 84 мм со всеми четырьмя leaf pairs; explicit frame преобразует оба witnesses независимо. Nearest hidden cylinder принадлежит полному составу; early-stop после zero запрещён контрактом. |
| B3-I12 /N4 | Aggregate point/axis: hidden nested cylinder outside point 3 мм /inside 6 мм, axis 2 мм /through 0 мм; explicit shifted/rotated frame обоих результатов. Leaf/body/face census и nearest original refs проверены; surface-only aggregate даёт отказ, не частичный success. |
| B3-I13 /N5 | Replay одного passive geometry/measurement read и одного guarded mass на прежнем request/payload: тот же operation/result, нет второго solver/calculation. Все I01…I12 имеют independent before/after selection marks/identity, view, dirty/file/config/active/visibility, geometry/rosters, CIP/lock и соседа. После terminal/quiescent calls закрыты только owned fixtures, полный исходный baseline восстановлен. |

Публичная приёмка — один представительный маршрут по каждой fixture-сессии:
все перечисленные read tools вызываются хотя бы один раз через stdio с exact
input/output schemas, `job_get` и durable journal. В неё входят document/object
roundtrip, repeated/nested membership, **каждый из восьми measurement tools**
(mass, bounds, три part-instance, три aggregate), explicit frame там, где он
поддержан, один foreign отказ и оба replay из I13. Подробные native rename/
delete/config отказные переходы I04…I06 не повторяются физически в public.
`measurement_prepare_mass` вызывается до mass; это отдельный tool, не девятое
числовое измерение. Public сохраняет собственную ownership/baseline проверку.

## Переиспользуемые стенды и конкретные пробелы

| Имеющееся средство | Что можно взять без нового CAD scope | Что мешает конечному B3 gate |
| --- | --- | --- |
| `verify_geometry_reads.py`, `verify_document_reads.py` | Part normal solid/surface, pagination/foreign/inactive/deleted geometry; document metadata. | Legacy harness assertions `13 tools`/единственная mutation `feature.rename` не соответствуют текущему catalog. `verify_geometry_reads.check` использует fixtures без supervisor cleanup gate; как готовый итоговый safety driver его запускать нельзя. Нужна внешняя интеграция этих checks с ownership/journal/unknown gating. |
| `verify_component_reads.py`, `verify_component_topology.py` + `verifier_component_fixtures.py` | I02/I03/I04…I06: repeated/config/nested/native identity, surface/cylinder topology, deletion/recreation. | Существующие CLI принимают только полные исторические internal/public наборы; public preflight требует их точные counts. Нет selective finite manifest B3 и общего same-wheel gate. |
| `verify_mass_properties.py --guarded-public-domain`, `verify_mass_mcp.py`, `verify_bounds_measurements.py` | I07/I08/I13: analytic oracle, selection restore, mass guard, rigid extrema и known отказ. | Проверка mass требует guarded domain, не старый passive mass backend. Public gates ожидают полные 22/14 internal cases; их accepted нельзя подставить от другого wheel либо сократить counts ради прохождения. |
| `verify_component_distance.py`, `verify_component_point_distance.py`, `verify_component_axis_distance.py` | I09/I10: independent metric, instance witnesses, explicit point/axis frames, native body/face refs. | Каждый driver выполняет отдельный полный internal/public профиль; общей fixture-сессии и сокращённого representational route нет. |
| `verify_component_aggregate_distance.py`, `verify_component_aggregate_probes.py`, `verifier_aggregate_fixtures.py` | I11/I12: 70/84 мм, 3/6/2/0 мм, complete census, frame projections, part-regression helpers. | Part regression в aggregate harness использует общий internal read path; не заменяет публичные отдельные part-instance tool/schema проверки. Public prerequisites также tied к полным historical counts. |
| `verify_dimension_mcp.py`, accepted B1/B2 receipts итогового wheel | I01/I04: exact feature/sketch/driving-dimension IDs, native length/units/rename membership. | Частные успешные creation/edit receipts не закрывают multiple-config/multibody/instance чтения. Нужны явные cross-links manifest→tool→receipt; старые размерные wheel evidence не подставляются. |

Самая малая доработка — **отдельный bounded B3 supervisor/manifest**, который
вызывает выбранные существующие checks/oracles и использует один современный
ownership/job protocol; не ослабление старых gates и не запуск всех исторических
drivers подряд. После завершения текущей frozen native-проверки сначала pure
проверить новый preflight/coverage/cleanup gates, затем выполнить native internal
и public на одном итоговом wheel. Здесь исходники/helpers не изменялись.

## Какие свидетельства закрывают пять условий

В локальных исторических файлах mass dev71, bounds dev72, component reads dev73
и topology dev74 пассивно подтверждены `accepted=true`, scopes/counts и SHA256,
совпадающие с их четырьмя опубликованными acceptance-документами. В public и
последних трёх internal отчётах также есть `fixtures_closed/baseline_restored`;
mass internal использует другую структуру полей, отсутствие этих двух ключей
не переобъявляется failure/success cleanup. Это **история тех wheel**; данные
CAD и журналы не экспортируются. Исторические distance/probe результаты описаны
в [контракте/приёмке агрегатов](COMPONENT_AGGREGATE_PROBES_ACCEPTANCE.md) и
смежных acceptance-документах; текущей native-валидации здесь нет.

Нужен приватный terminal report нового B3 с точными wheel SHA256/version/Git/
source digest, installed metadata и verifier/helper hashes; все I01…I13 с
сырыми независимыми native receipts и public tool/job mapping. Gate проверяет
пять N-условий, объявленные numerical tolerances каждого oracle, отсутствие
необъяснённых skipped/unknown, полностью возвращённые native calls, exact-owned
cleanup, initial/restored baseline. Read summaries/stamp/mass не заменяют
полную требуемую наблюдаемую область сохранности. Rebuild/recovery/restart
гарантии B4 и release/CI B5 подтверждаются своими gates.

**Блокирует закрытие B3:** отсутствуют конечный bounded supervisor/общий gate,
native internal/public evidence перечисленного набора на итоговом wheel и
manifest связь с переиспользуемыми итоговыми B1/B2 чтениями. Новый доменный
CAD-функционал для этого набора заранее не требуется; обнаруженная регрессия
существующего scope исправляется до принятия. Статусы плана не изменены.

## Реализованная подготовка стенда — 12.10.2026

Добавлены отдельные внешние модули, без изменения установленного dev93,
исходников пакета и helpers текущего native B1:

- `verifier_b3_manifest.py`: точные13 групп и покрытие27 tools; две fixture-сессии,
  fresh supervisor gate перед/после каждого handler, сохранение running до
  dispatch. Ошибка native/protocol/storage или cancellation не запускает следующий
  handler и не выполняет автоматическую очистку. Replay собирается внутри живой
  соответствующей сессии; I13 проверяет собранные receipts и итоговый baseline.
- `verifier_b3_public_contract.py`: defaults/constants и настоящая normalization
  всех27 фасадов, включая вложенные StrictFloat vectors/rigid frames. Единственный
  guarded mutation здесь — mass. Проверено через настоящие create_app и
  Runtime._dispatch, без исполнения callbacks/worker/CAD.
- `verifier_b3_journal.py`: fresh supervisor proof, полная job_get/независимая
  SQLite сверка, исходные request/payload/digest, exact mass checkpoint и replay.
  В SQL observation mutation=None присутствует, passive DTO его не содержит;
  разрешено только это известное различие decoder, не отбрасывание иных полей.
- `verify_b3_preflight.py`: offline artifact/installed identity и повторное
  использование exact-wheel metadata report, manifest/catalog/helper hashes.
  Нет нового SDK subprocess или CAD; can_start_native=false и
  native_acceptance=false остаются явными.
- `verifier_b3_witnesses.py`: общий pure oracle шести component-измерений;
  absolute metric/frame tolerance1e-6 мм, root/local correspondence,
  нормализованная бесконечная ось, принадлежность точки оси и перпендикулярность
  кратчайшего отрезка. Native boundary/minimum/census по-прежнему доказывают
  независимые физические проверки конкретного CAD handler.

Related integration: **254 passed /18,27 с** (новые modules и существующий
supervisor). После уточнения полной SQL schema и двух новых cases: **24 journal
passed /0,68 с**; набор перекрывается с integration. Preflight: **18 passed**.
Первая попытка временных SQLite tests была ограничена доступом sandbox и не
засчитана; окончательные проверки выполнены в отдельных каталогах проекта.

Offline preflight exact installed dev93 принят:13 groups/27 tools, без source
PYTHONPATH, native_acceptance=false. Private итоговый отчёт
`work/b3-preflight-dev93-final.json`. Промежуточные preflight сохранены отдельно
и не используются как актуальный helper manifest. После интеграции witness
oracle итоговый related-набор: **294 passed /18,44 с**; private log
`work/b3-related-final-1.log`. Это один набор с перекрытием предыдущих проверок,
не сумма дополнительных native-случаев.

Это подготовка общего контура, **не законченный native driver и не приёмка B3**.
Остались конкретные installed/native handlers с независимыми полными snapshots,
аналитическими oracles и exact fixture ownership/cleanup, public маршрут и
строгий общий acceptance gate. Запуск CAD B3 выполняется после текущего B1 и
согласованного B2; искусственное выполнение callbacks не объявляется passed CAD.

Следующий подготовленный слой — `verifier_b3_reader.py`: один tracked durable
send, late polling того же operation_id, исходный tool acknowledgement и полная
job_get/SQLite сверка. Первичный terminal tool result нельзя подменить правильным
последующим job_get. Known failed read принимается только с явным ожидаемым code;
unknown и протокольное расхождение удерживают маршрут без дальнейшего dispatch.
Cancellation ожидания не вызывает job_cancel или повтор. Replay сохраняет весь
terminal row и явно заданный тип ожидаемого исхода.

При сверке с настоящим job_get исправлена первоначальная ошибка нового стенда:
outer status известного отказа тоже failed. Проверяются operation_id, status,
context и error внешней оболочки, затем полный DTO/SQL row. Новые tests используют
настоящие JobStore и публичный job_get; callbacks CAD запрещены.
Итоговый совместный related-прогон B3 reader/journal/preflight и B4 barrier:
**89 passed /5,03 с**; private `work/reader-barrier-integration-1.log`.
Актуальный offline helper manifest: `work/b3-preflight-dev93-reader-final.json`;
прежние preflight сохранены как история. Concrete native handlers/B3 acceptance
gate остаются открытыми.

13.10.2026 подготовлен конкретный finite public handler B3-I02 —
`verifier_b3_part_geometry.py`: три тела, полный face/edge census,
пагинация limit2 первого solid, семь representative list→get roundtrips,
аналитические area/length, foreign/inactive отказы. Все44 listed references
требуют независимый native owner/membership receipt; before/after требуют
полного part/neighbor/session proof. Никаких fixture creation, suppression,
cleanup или COM-вызовов в helper нет; accepted/native_acceptance остаются false.
Producer должен наблюдать фактическую CAD геометрию, а не повторять tool summaries.

Связанный pure-набор handler/reader/journal/manifest — **82 passed /4,12 с**;
handler использует искусственные public/native fixtures, остальные связанные
тесты — настоящий JobStore/SQLite/job_get. Это не native B3. Exact installed
dev94 offline preflight принят13/27 (`work/b3-preflight-dev94-1.json`), без SDK
subprocess/CAD; он не разрешает занятую сессию. Нового wheel/full pure/push нет.

`verifier_b3_bounds_oracle.py` готовит независимый B3-I08 analytic support:
углы заданных прямоугольников/плоскости и support кругового сечения цилиндра,
без приближённого AABB fallback. Строго проверяются все3 координаты, complete
distinct body census, explicit frame/query, native method/read postconditions
и absolute tolerance1e-6 мм. Усечённые vectors, nonfinite/bool и reflection
отклоняются; planar zero extent поддерживается. Это пассивный oracle, без CAD.
Свои36 pure cases прошли0,15 с. Общая интеграция новых B2/B3 preparations —
**200 passed /7,79 с**; этот набор перекрывает указанные выше related-прогоны.
Concrete native producers/handlers остальных групп и final B3 gate остаются.

Следующий concrete route `verifier_b3_part_bounds.py` использует live I02
reference receipts и выполняет ровно7 durable reads: cylinder census,
четыре positive bounds, foreign body и stale observation. Без переключения
конфигураций, скрытия тел, fixture edits и повторного общего body census I02.
Четыре результата проходят analytic oracle; независимый observer подтверждает
actual radius6/length30/model-Y cylinder и полный before/after session.
Прежние wheel/retired refs или неполный I02 перед dispatch отвергаются.

Reflection input публичный typed schema отвергает до durable job; эта source/
schema проверка не подменяется выдуманным public job. Internal domain rejection
остаётся отдельным manifest assertion. Route — evidence preparation, accepted/
native_acceptance/cleanup=false, не полный B3-I08 native gate.
Свои14 pure /0,18 с; related route/I02/oracle/reader/journal —
**114 passed /4,18 с**. New geometry fixtures искусственные, CAD не вызывался.

Concrete `verifier_b3_part_mass.py` выполняет две prepare→guarded mass цепочки
с live I02 IDs: все solid и explicit второй, всего4 sends. Native producer
независимо подтверждает одинаковые effective densities обоих блоков (1e-12),
document/body no-overrides, hidden второй solid, исключённую surface и исходное
выделение первого solid того же part. «Foreign UI selection» здесь означает
другое тело относительно explicit scope, не документ-сосед. Canonical ordinal
назначается по удерживаемым IUnknown equality; PID — canonical lowercase hex,
не имена/адреса указателей. Native whole part/neighbor/session/selection/density
должны точно сохраниться до/после каждой цепочки и между ними.

Объём2000/1000 мм³, area1400/700 мм², COM30/50,5,2.5 мм и масса проверяются
по независимым density receipts; единицы/tolerances указаны раздельно. Actual
B3Reader/JobStore/SQLite/public job_get подтверждают mutates=True/committed
checkpoint; unknown/missing checkpoint удерживают route без redispatch.
Свои65 pure cases —1,12 с. После review итоговая related integration новых
B2/B3 preparations — **309 passed /10,27 с**, с искусственной геометрией и
реальным durable protocol. Это не CAD-приёмка B3; final native producers/gate
и остающиеся manifest groups открыты. Installed dev94/B1 helpers не менялись.

Подготовлен `verifier_b3_component_membership.py` для конечной группы I03:
пять исходных component IDs, повторный файл/две конфигурации/вложенный instance,
current canonical/PID/16-value total transforms, body rosters3/2/2, body/topology
roundtrips и пять конечных foreign-reference отказов. Полное состояние сборки,
referenced parts и соседа проверяется до/после; имена и порядок перечисления
не дают владение. **233 related pure passed /23,69 с** с реальными catalogs,
JobRunner/SQLite/B3Reader и искусственными native handles. Actual native
producers, exact installed B3 driver и terminal cleanup остаются открыты;
accepted/native_acceptance/cleanup_authorized=false, manifest не расширен.

Сверка с actual `verifier_component_fixtures.py` исправила исходное ожидание
вложенного экземпляра: он использует «Вариант», как второй root instance,
а не «Основная». Поэтому nested roster имеет2 тела, canonical configuration
совпадает с variant, не main. Это исправление source route, не смена native
fixture и не результат CAD-приёмки.

После исправления I03 профиль совпадает с существующим native setup:
**233 related pure passed /25,35 с**. Actual CAD-проверка I03 не запускалась.

Metadata-подмаршрут I01 подготовлен отдельно в
`verifier_b3_document_metadata.py`: document_list и document_get двух исходных
held part IDs во всех явно переданных1–2 существующих конфигурациях. Native
observer обязан независимо читать metadata/current model/configuration anchors;
inactive metadata не разрешает activation. Exact list/get revision и полный
before/after session сверяются, результаты связаны с actual SQLite журналом.
**201 related pure passed /18,06 с** с искусственными native handles и реальными
DocumentCatalog/JobRunner/B3Reader. Feature/dimension/sketch часть I01, actual
native producers, installed B3 driver и cleanup остаются открыты. Никаких
accepted/native/cleanup разрешений этот source-подмаршрут не выдаёт.

I09 `verifier_b3_instance_distance.py` подготовлен для ровно двух durable pair
reads существующего assembly-профиля: main→variant15 мм и main→nested70 мм.
Независимые current canonical/PID/total-transform receipts, полный solid/surface
census, исходные trimmed-boundary witnesses в local/root frame и более близкая
surface подтверждаются отдельными producer callbacks; поверхности исключены
из solid minimum, hidden solid включён. **279 related pure passed /21,89 с**
через реальный ComponentDistanceCatalog/JobRunner/SQLite/B3Reader с искусственным
BREP. Actual native producers, same-wheel B3 driver и cleanup открыты;
accepted/native/cleanup остаются false. I10–I12 этим маршрутом не закрыты.

Feature/dimension подмаршрут I01 подготовлен в `verifier_b3_part_objects.py`:
полный finite census активной part, поддержанные list→get refs и неизменная
domain revision; неподдержанные native строки имеют только null ID и объявленную
reference error. Независимые native inventory/current anchors сверяются до/после,
значения SI переводятся в mm/deg без догадок о единицах документа. Полная part,
сосед и UI/session сохраняются. **290 related pure passed /20,45 с** с настоящими
FeatureCatalog/DimensionCatalog/JobRunner/SQLite и искусственными native handles.
Native producers, installed driver и отдельный sketch_get на same-wheel B1
пластине остаются открыты. Source маршрут не разрешает acceptance/cleanup.

Последний I01 source-подмаршрут `verifier_b3_rectangle_sketch.py` выполняет один
`sketch_get` исходной same-wheel B1 пластины с единственной конфигурацией.
Full current sketch snapshot, sketch/plane/origin/member bindings, исходные
PID/canonical, размеры и полный constraint graph связываются с отдельными
native producer receipts; raw dimension semantic используется для rectangle
classification. Полный original part/neighbor/session и native proof сохраняются
до/после. **250 related pure passed /20,45 с**, реальный SketchCatalog/JobRunner/
SQLite и искусственный native эскиз. Это завершённая source-подготовка чтений
I01, но actual original native producers, installed B3 driver и cleanup пока
открыты; B3/I01 native acceptance не объявлена.

I10 `verifier_b3_instance_point_axis.py` подготовлен для трёх durable reads:
variant point в explicit frame → trimmed corner √425 мм, cylinder axis gap2 мм
и пересечение осью с нулевым расстоянием. Current instance/body/face census,
original PID/canonical, raw total transform, local/root witnesses и actual point
location сверяются независимыми producer callbacks; для zero допустима actual
inside либо подтверждённая boundary точка, без выдуманной interference
классификации. **337 related pure passed /23,89 с**, настоящие point/axis catalogs,
JobRunner/SQLite/B3Reader и искусственные native getters. Actual native producers,
installed B3 driver и cleanup открыты; accepted/native/cleanup остаются false.

I13 replay source-подмаршрут `verifier_b3_replay.py` переиспользует две actual
original receipt records: passive geometry/bounds и committed guarded mass
того же part/configuration. Каждый replay связывается с полной исходной raw
SQLite строкой; весь journal до/после, current session и owner epoch сохраняются.
Два отдельно инструментированных счётчика — selected domain dispatch и mass
calculation — не растут; они не объявляются полным COM census. **230 related
pure passed /19,41 с** через настоящие GeometryCatalog/MassMeasurementCatalog/
JobRunner/SQLite/B3Reader и искусственные native getters. Actual owner native
scope/activity producers, installed B3 driver, завершение I01…I12 и terminal
owned cleanup остаются открыты. Source evidence не даёт native/cleanup acceptance.

I11 source `verifier_b3_aggregate_distance.py`: ровно две durable aggregate pair
reads существующего профиля — part→subassembly70 мм и repeated subassemblies84 мм
в explicit frame. Current original targets/leaves, полный solid/surface census,
все2/4 фактически вычисленные leaf pairs (включая nonwinning) и hidden cylinder
сверяются с отдельными native receipts; оба witnesses независимо преобразуются
между local/root/explicit frames. **393 related pure passed /25,53 с** через
настоящий ComponentAggregateDistanceCatalog/JobRunner/SQLite/B3Reader и
искусственные native getters. Actual owner census/PID/all-pair/trimmed-boundary
producers, installed B3 driver и terminal cleanup открыты; native/cleanup
acceptance остаётся false. I12 и native transitions I04…I06 этим не закрыты.

I12 source `verifier_b3_aggregate_point_axis.py` подготовлен: четыре positive
aggregate point/axis reads3/6/2/0 мм, explicit shifted/rotated frame в тех же
outside/gap случаях. Current original full leaf/body/face census, все leaf probes,
actual point location/axis support и hidden nearest cylinder refs сверяются
отдельными native producers. **402 related pure passed /25,79 с** через настоящие
aggregate probe catalogs/JobRunner/SQLite/B3Reader и искусственные native getters.
Surface-only refusal — отдельная owner-prepared фаза subassembly«Вариант» /
child«Основная» после явного fixture setup: свежие context/IDs, полный surface+
empty-cylinder census, один `component_has_no_solid_bodies`, no mutation.
Helper не выполняет setup/setter. Actual setup ownership/postconditions,
native producers, installed B3 driver и cleanup открыты; acceptance=false.

I04 source `verifier_b3_rename_references.py` проверяет три original-ref reads
после отдельно acknowledged own rename: feature_get, component_get и исходная
face через component_topology_get. Part принадлежит тому же retained referenced
model, body/face — прежнему component owner. Raw old-PID resolution должен
вернуть прежний canonical объект; current PID alias и новое enumeration ID
допустимы без потери старой ссылки. Одинаково выглядящие replacement/foreign
объекты отвергаются. Native rename receipts и exact allowed-change scope остаются
отдельным gate; source helper не выполняет setters.

I05 source `verifier_b3_component_retirement.py`: две отдельные passive фазы
после acknowledged original-owner delete/reinsert. В каждой — три old-ref
отказа с exact before-dispatch producer code; reinserted добавляет три
current owned-ref roundtrips новой инкарнации того же файла. Raw PID/canonical,
отсутствие original в текущем census и critical paired native receipts
проверяются, но не подменяют whole transition ownership/postconditions.
**280 related pure passed /20,08 с** для I04/I05 с настоящими catalogs/JobRunner/
SQLite/B3Reader и искусственными уже подготовленными native phases. Actual
native producers/transitions, installed B3 driver и cleanup остаются открыты;
source accepted/native/cleanup=false. I06 ещё не подготовлен.

I06 source `verifier_b3_configuration_references.py` завершён: separate
referenced-configuration phase9 reads и part-configuration phase2 refusals.
Same original model/instance/PID, разные old/current configuration anchors,
полный roster2→3 и новые current owner refs; сохранение body canonical допустимо.
Old part ref даёт `object_configuration_mismatch`, inactive geometry —
`configuration_not_active`; inactive metadata остаётся читаемой. **328 related
pure passed /20,81 с**, реальные catalogs/JobRunner/SQLite/B3Reader с
искусственными уже подготовленными phases. Native setup/full allowed-change
scope/ownership, actual producers, installed driver и cleanup остаются открыты.

Все13 named source routes подготовлены; [native driver map](B3_NATIVE_DRIVER_MAP.md)
фиксирует конечные подключения и оставшиеся gates. Offline exact installed
dev96 preflight принят:13 groups/27 required tools, metadata report reused,
без CAD/SDK запуска. `can_start_native=false`, B3 native ещё не принят.

Итоговая [source-контрольная точка](B3_SOURCE_CHECKPOINT_DEV96.md):
**9952 pure passed /514,75 с**,323 CAD deselected. Это полный current source,
не native acceptance. Package/wheel96 и22 live fault helpers неизменны.

После этой checkpoint начата concrete producer integration I02:
`verifier_b3_native_part_reference.py`,107 related pure/4,20 с. Direct raw
body/plane/line getters, retained canonical/PID/current owner и весь original
body census; extra body/replacement/unsupported geometry/ABA дают отказ.
Это следующий source-блок, не часть прежнего9952 результата и не actual CAD
acceptance. Whole-session/namespace/owner integration остаётся открытой.
