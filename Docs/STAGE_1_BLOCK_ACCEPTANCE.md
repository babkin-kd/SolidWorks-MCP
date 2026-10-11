# Конечная приёмка блоков стадии 1

Этот документ задаёт критерии завершения, а не объявляет приёмку пройденной.
Статусы и свидетельства ведутся в [PLAN.md](../PLAN.md),
[матрице требований](STAGE_1_REQUIREMENTS_MATRIX.md) и
[аудите](PLAN_STATUS_AUDIT.md). Каталог содержит только реализованные операции:
[API v2](API_V2.md). Исторический accepted scope подтверждает только свой wheel.

Сохраняются три стадии: **1 — исправление; 2 — основной функционал;
3 — дополнительный функционал**. Ниже конечная минимальная область стадии 1;
широкие требования остаются видимыми в отдельных задачах, без статуса passed.
Закрытие строки S1-xx относится к этой области; перенос её расширений указывается
в матрице и миграции явно.

## Обязательные гарантии каждого поддержанного случая

1. Документ, конфигурация и объект заданы явными ID; имя служит отображению,
   а не идентификации. Prepare/read не изменяют модель, выбор и активную цель.
2. Изменение требует полной поддержанной ревизии и `request_id`. Проверка
   контекста выполняется до первой записи; старый/чужой ID, stale revision,
   неподдержанное состояние и неполный inventory отклоняются до эффекта.
3. COM исполняется последовательно в одном STA. Durable checkpoint и журнал
   native-шагов предшествуют эффектам; timeout означает только конец ожидания.
4. Success требует независимо проверенных CAD/файловых постусловий. Known failure
   требует доказанного отсутствия эффекта либо полного scoped восстановления.
   Неподтверждённый исход остаётся unknown с hold; native-вызов не повторяется.
5. Replay возвращает прежнее задание без нового эффекта; другой payload при том же
   `request_id` отклоняется. Reconnect/restart не обходят hold или незавершённый COM.
6. Dirty сосед сохраняет геометрию, конфигурацию, dirty flag, файл и UI.
   Остальной baseline включает roster, окна, selections/view, CWD и настройки.
   Допустимое изменение активного документа задано явно контрактом lifecycle.
7. Новые детали/эскизы/элементы и пользовательские метки — по-русски, с exact
   readback. Файлы библиотек, артикулы и обозначения стандартов не переименовываются.
8. Очистка касается только доказанно собственных контрольных документов после
   завершённых вызовов. Она не превращает unknown в success; при hold документы
   и журнал сохраняются до доказанного согласования состояния.

Эти гарантии **не переносятся** в стадию 2 вместе с расширенными входами.
Отказ от неподдержанного случая входит в приёмку поддержанного scope.

## Единый бюджет доказательств

Для каждого блока обязательны три слоя:

| Слой | Конечный gate |
| --- | --- |
| P — pure | Связанные проверки входов/границ/ревизий/receipt/журнала, success/known failure/unknown, replay/conflict. Полный pure-набор перед итоговым wheel блока и при изменении общего контура; пропущенные CAD-тесты отдельно, без зачёта |
| I — installed | Два условия: I1 exact version/Git/source digest/wheel hash и фактический tools/list/schema без `PYTHONPATH`; I2 настоящий stdio-фасад и durable job-контракт поддержанных запросов. Искусственные runtime-тесты этого не заменяют |
| N — native | Указанные ниже конечные условия на exact установленном wheel. Internal проверяет подробные отказы/восстановление; public MCP — пользовательскую цепочку, контракт и журнал. Общие физические случаи не дублируются без причины |

Числа ниже — **условия приёмки**, а не число pytest-тестов или требование запускать
отдельную CAD-сессию на каждый пункт. Общие гарантии проверяются поперёк условий.
Новые случаи добавляются только для обнаруженного дефекта или нового согласованного
scope. Изменение verifier требует повторной проверки его затронутых gates;
правка обычной документации сама по себе не требует CAD.

## L2 — открытие native-документа

**Результат:** пользователь открывает подготовленный точный файл и конфигурацию,
получает ID корневого документа и доказанные новые/заимствованные ссылки.
Scope уже реализуется отдельно; эта матрица его не расширяет.

**Вход/выход/ошибка:** native part/assembly/drawing в принятом resolved scope,
явные filename/type/configuration/read-only и prepared native_file_id/revision.
Выход — exact root, new/borrowed IDs, reference graph и native receipt.
Loaded source, отсутствующая конфигурация, stale, чужой alias/resolution,
неподдержанные режимы и неполный census не дают success. Clean rollback возможен
только для доказанно собственных новых handles; throws/foreign/dirty delta дают hold.

**N: 7 условий.** (1) Part: exact configuration, geometry и read-only.
(2) Assembly и drawing: точные resolved new/borrowed references и referenced
configurations. (3) Dirty сосед и baseline сохранены.
(4) Replay/stale/loaded/missing configuration до записи.
(5) Нормальный no-effect отказ и scoped own-clean rollback.
(6) Изменившийся CWD восстановлен one-shot шагом с ledger и независимым readback;
чужой каталог, pending или недоказанный возврат блокируют завершение.
(7) Exact-owned cleanup и полный baseline восстановлены.
Фактические internal/public labels задаёт [контракт L2](NATIVE_DOCUMENT_OPEN.md),
а не новый расширенный перечень физических сценариев: текущий конечный manifest
содержит 13 internal /11 public cases. Они не считаются пройденными по частично
успешному прогону или committed отдельной операции.

## L3 — первое native-сохранение

**Результат:** собственная новая деталь становится проверенным native-файлом;
пользователь получает явно привязанный документ для дальнейшего Save3.

**Вход/выход/ошибка:** own unsaved part, одна конфигурация/один solid, без
incoming/outgoing refs; явный новый путь на поддержанной локальной FS.
Выход — сохранённый путь/file identity и document/object ID mapping, включая
retirement старых ссылок при replacement identity. Существующий/raced destination,
неподдержанный parent/refs, stale и неполный receipt блокируют публикацию либо
оставляют доказанный известный/неизвестный исход; overwrite запрещён.
Нативная запись копии без привязки итогового документа не закрывает L3.

**Граница baseline:** dirty сосед — самостоятельная контрольная part того же
полностью наблюдаемого профиля прямоугольного основания. Другой неподдержанный
сосед или неизвестные данные шаблона отклоняются до SaveAs; сохранность
произвольной модели не объявляется доказанной. Учёт стандартных служебных
данных поддержанного шаблона нужен для полного снимка, но не требует добавлять
инструменты их редактирования. Более широкий baseline L2 задан его контрактом.

**N: 6 условий.** (1) First save и независимый native readback формы, дерева,
размеров и конфигурации. (2) Итоговый документ/path и ID mapping пригодны для
close/open/следующего Save3. (3) Destination conflict и race не перезаписывают
чужой файл. (4) Native false/warning/throw классифицированы по реальному эффекту;
нет повтора, cleanup только owned/terminal. (5) Stale/replay и сохранность dirty
соседа. (6) Чистая roundtrip-цепочка завершает baseline.
Подробный протокол no-replace/staging/replacement остаётся отдельным
[проектом lifecycle](NATIVE_DOCUMENT_LIFECYCLE_DESIGN.md): до native-доказательства
его нельзя объявлять реализованным атомарным SaveAs.
Конечное распределение этих шести условий между внутренними проверками и
публичной цепочкой: [набор приёмки L3](NATIVE_FIRST_SAVE_ACCEPTANCE.md).

## S1-B1 — явная плоскость, эскиз и базовое выдавливание

**Результат:** создать русскую деталь «Контрольная деталь», выбрать существующую
native plane по ID, получить отдельный прямоугольный эскиз «Эскиз основания»
и blind extrusion «Основание» с доступными размерами.

**Вход/выход/ошибка:** активная конфигурация поддержанной детали, plane ID,
размеры прямоугольника и положительная глубина в явных единицах; затем явный
sketch ID для extrusion. Выход — IDs, revision, actual geometry/параметры и
русские имена. Чужая/заменённая плоскость, open/неподдержанный профиль,
неполные связи, stale и чужой target отклоняются до записи.

**N: 5 условий.** (1) Полный create → plane → sketch → extrude с аналитическим
BREP/объёмом и actual dimension readback. (2) Выбрана точная plane/orientation,
сосед и чужие объекты сохранены. (3) Русские имена и object membership.
(4) Stale/replay и отказ неподдержанных inputs.
(5) Известный сбой новой операции: scoped restoration либо unknown/hold при
недоказанном возврате. Создание произвольных вспомогательных плоскостей — D2-GEOMETRY.

## S1-B2 — размер, имя, подавление и удаление

**Результат:** изменить driving length собственного базового элемента,
переименовать его по-русски, подавить/восстановить или удалить точно выбранный
own leaf с предварительным impact preview.

**Вход/выход/ошибка:** явные dimension/feature IDs, активная конфигурация,
revision, новое length/name/suppression или prepared deletion impact.
Выход — actual значение/имя/состояние, точный удалённый набор и новая revision.
Linked/read-only/неподдержанный размер, dependent feature, equations/annotations/
external/incoming refs, неполный inventory или stale запрещают запись.
У own leaf весь поддержанный inventory обязателен: пустота dependencies доказывается.

**N: 6 условий.** (1) Length edit/readback/rebuild изменяет ожидаемую форму.
(2) Rename/readback сохраняет устойчивую ссылку.
(3) Suppress → unsuppress восстанавливает exact own geometry/history.
(4) Preview read-only; execute удаляет только подтверждённый own leaf,
старый ID больше не принимается. (5) Dependency/linked/stale/replay отказы.
(6) Известный scalar/create/delete сбой восстанавливает поддержанный scope,
недоказанный эффект удерживается; dirty сосед и конфигурации вне цели сохранены.

## S1-B3 — адресация и измерения

**Результат:** однозначно прочитать документ/элемент/тело/границу/размер;
получить массу, габариты и расстояния с явными единицами и frame.

**Вход/выход/ошибка:** поддержанные part и малая resolved assembly, explicit
instance paths/configurations/transforms; normal solid/surface в пределах
контракта каждого чтения. Измерения используют только заявленные solid scopes,
model/root либо переданный rigid frame. Выход — актуальные IDs, units/frame,
числа и witnesses. Foreign/deleted/replaced refs, unsupported load/topology/frame
и неполный aggregate отклоняются, а не заменяются приближением.

**N: 5 условий.** (1) Два документа, чтение нескольких конфигураций и multibody
membership без скрытой активации. (2) Повторные экземпляры одного файла различены
по instance/configuration/transform. (3) Rename сохраняет refs; delete/recreate/
configuration replacement отвергают старые refs. (4) Аналитические mass/bounds/
distance и units/shifted-rotated frame/witnesses в поддержанных scopes.
(5) Selection/view/dirty сосед сохранены; replay возвращает тот же read result.
Исторические scopes берутся из их контрактов; итоговый wheel подтверждается
конечным representational набором N1/N2, а не суммой всех прежних native-прогонов.

## S1-B4 — диагностика и восстановление

**Результат:** увидеть стадию/исход задания, дождаться позднего результата,
безопасно согласовать unknown и получить timings без лишнего CAD-потока.

**Вход/выход/ошибка:** operation_id/request_id, explicit target и private job
store; bounded diagnostics фильтры. Выход — durable status/checkpoint/hold,
раздельные timings и доказательство reconciliation. Нельзя отменить исполняющийся
COM, обойти hold новым ID/epoch или считать failure диагностики ошибкой геометрии.

**N/installed: 6 условий.** (1) Реальный исходный rebuild-дефект отличён от нового,
новый дефект не маскируется success. (2) Known scoped restoration параметра/новой
операции, а недоказанный эффект — unknown. (3) Late native completion после timeout
без повтора, request conflict/replay, только queued cancel.
(4) Restart собственного server-процесса после завершения CAD-вызова сохраняет
unfinished→unknown/holds; reconnect и новая эпоха их не обходят.
(5) Reconciliation по независимому exact scope proof; другая цель доступна лишь
если не удерживается application scope. (6) Diagnostics enabled/disabled/error,
bounded storage/privacy и end-to-end/queue/COM/rebuild/restore intervals из этих
же прогонов; ошибка telemetry не снимает обязательный journal.

## S1-B5 — сквозной выпуск

**Результат:** пользователь выполняет конечную цепочку на одном exact installed
wheel через публичный MCP, сохраняя открытый dirty сосед:

1. Создать русскую деталь.
2. Адресовать существующую native plane.
3. Создать прямоугольный эскиз.
4. Выдавить базовое основание.
5. Изменить driving length и проверить форму.
6. Выполнить первое native-сохранение; принять документ/ID mapping результата.
7. Закрыть точный чистый документ.
8. Открыть файл/конфигурацию; проверить дерево, размеры и форму заново.
9. Изменить размер явно адресованного элемента.
10. Сохранить текущий native-файл через Save3 и независимо перечитать результат.
11. Закрыть свой документ и доказать исходный baseline.

**Поддержанный результат/ошибка:** все переходы используют актуальные IDs,
configuration/revision/request_id. Known refusal сохраняет проверенный baseline;
unknown останавливает зависимые записи с hold. Весь сценарий accepted только
при доказанной форме/файле/журнале и cleanup, а не по успешному последнему вызову.

**Приёмка: 11 условий цепочки + 4 release gates.** G1: манифест покрытия
L2/L3/B1–B4 → поддержанные части S1-01…22/N0–N6, без необъяснённых skipped/unknown.
G2: полный pure/build и exact installed tools/schema/stdio; старые wheel-отчёты
не подменяют текущие свидетельства. G3: измеренные timings/COM dispatches этого
конечного сценария без ослабления snapshots и postconditions.
G4: локальный пакет изменений, согласованные migration/каталог/документы,
затем цельный PR в форк с обязательным CI; публикация отдельным согласованным шагом.
Стадия 1 не закрывается одним CI или выполнением только L2.

## Видимые расширения за границей минимального выпуска

Каждая строка — незакрытая задача. Её конечный тестовый профиль фиксируется до
реализации; общий контракт безопасности выше распространяется на новые inputs.

| ID / стадия | Расширение и конечный критерий |
| --- | --- |
| D2-LARGE /2 | Сборки 1000+: одна согласованная fixture >1000 instances; полный census и refs заявленной области без принудительного полного resolve, пять exact выбранных компонентов, сохранность baseline и измеренные время/память/COM dispatches |
| D2-LOADREF /2 | Lightweight/suppressed/SpeedPak/LDR/detached/assembly-cut и неоднозначные refs: explicit allow/reject на один fixture каждого заявленного режима; никакого silent partial результата |
| D2-FRAMES /2 | Native named frames: точное разрешение имени→ID/frame, transformed analytic witnesses, rename/stale/foreign-frame отказы |
| D2-CLOSE /2 | Dirty-owned/retained-reference close и выгрузка: explicit discard/retirement policy, incoming refs, доказанные postconditions; закрытие окна не объявляется unload |
| D2-DOCUMENTS /2 | Пустые assembly/drawing, их first save/refs и самостоятельная activation: каждый заявленный тип проходит create/save/open/close, exact active-after и сохранность чужих документов |
| D2-CONFIG /2 | Multi-config/multi-body mutations и семейства: изменение только explicit cfg/body, остальные snapshots неизменны; properties/table/BOM readback для заявленного семейства |
| D2-DIMENSIONS /2 | Signed/angle/tolerance/linked controls: actual sign/unit/tolerance/driving semantics каждого разрешённого типа, запрещённые controls до записи, restore доказан |
| D2-DELETION /2 | Произвольный граф/equations/annotations/external deps: полный preview каждого класса связи, exact execute/restore и отказ incomplete inventory |
| D2-DIAGNOSTICS /2 | Workload grouping/full COM census/performance: фиксированные workload fixtures, счётчики и p50/p95 на заданной выборке, сравнение без ослабления safety |
| D2-GEOMETRY /2 | Вспомогательные planes, spline/3D/sweep/loft/поверхности и ремонт импорта: explicit fixtures каждого заявленного scope, независимый BREP/parameters и known/unknown recovery |
| D2-SHEET /2 | Листовой металл: предприятие задаёт K; native folded/flat geometry, bend parameters и roundtrip для каждого нового заявленного профиля; прежние scoped receipts сохраняются как история |
| D2-WELD /2 | Профили/рамы/cut lists: библиотечный профиль и length/trim/joints плюс actual cut-list readback, без переименования library SKU |
| D2-DRAW /2 | ЕСКД/ГОСТ и шаблоны предприятия: один согласованный комплект drawing/views/dimensions/BOM, native associations и проверка оформления по шаблону |
| D2-LIBRARY /2 | Максимальное использование стандартных изделий: approved library fastener из существующего файла/config, повторное использование экземпляров, сохранность файла/SKU/standard и exact assembly refs |
| D2-PDM /2 | PDM Professional: sandbox vault receive/version/checkout/checkin на своих файлах; rights/conflict/no-double-checkin и preservation локальных изменений |
| D2-DISTRIBUTION /2 | Публичное имя пакета/публикация: отдельно согласованные name/license/attribution, exact accepted release artifact и проверенная установка; PyPI-публикация не предварительное условие локального S1-B5 |
| D3-KINEMATICS /3 | Движение/зазоры: один согласованный механизм и конечный набор положений/траектория, проверенные contacts/clearances и исходное состояние |
| D3-SIM /3 | Статическая прочность сборки с контактами: контрольная сборка, loads/fixtures/materials/contacts/mesh convergence и проверяемый результат solver |
| D-DEFER-IMPORT /3, отложено | STEP/IGES/Parasolid импорт/экспорт возвращается отдельным решением: roundtrip type/units/geometry/refs на конечном наборе своих файлов |
| D-DEFER-STL /3, отложено | STL/3MF/печать/сетки возвращаются отдельным решением: конечные geometry/unit/tessellation cases и exact preferences restoration; текущий экспорт не блокирует стадию 1 |

Подготовка этой спецификации не запускает CAD, wheel или GitHub CI.
Приватные модели, шаблоны, PDM-данные и job-отчёты остаются вне публичного Git.
