# Штатная отбортовка — разработка сценария

## Кандидат цельного сценария

Подготовлены доменный writer, runtime и MCP-фасад:
`sheet_prepare_edge_flange` / `sheet_create_edge_flange`, scope
`single_l_sheet_edge_flange_v1`. Dev64 не принят; готовится dev65, принятой сборкой
остаётся dev63. Первый scope: согнутый собственный L-профиль, горизонтальная
фиксированная полка, одно тело/конфигурация, полное внутреннее продольное ребро;
одна отбортовка90° внутрь. Длина до наружного виртуального пересечения, r2 и
K2 обязательны. Исходные размеры, первый сгиб/K и имена сохраняются.

Домен проверяет два полных closing capture до/после записи, весь U-BREP,
независимые native-параметры и полный профиль/driver. Durable checkpoint — до
STA guard. Восстановление допускает только полный собственный input либо
completed U; неполное/чужое состояние остаётся unknown. Request_id не повторяет
создание, timeout не отменяет COM. Dev64:3856 pure/323 CAD deselected, installed metadata46/16 прошли.
Native invalid/stale подтверждены; input-restoration остановлена на сравнении
transient original relation wrappers после namespace. Unknown сохранён.
Исправление фильтрует только relation addresses до добавления prefix;
полные relation semantics и сильные entity references остаются обязательными.
Pending creation/deletion/selection receipt всегда удерживает неизвестный исход.
Native-приёмка dev65 ещё нужна.
Развёртка U/углы/разгрузки и произвольные листовые детали остаются расширениями.

## История исследования перед кандидатом

Source23 прошла новое source-edge binding, но остановилась на closing comparison
anonymous-plane COM view/transform до factory. Private unknown сохранён; sketch
и driver возвращены, profile_before не доказан, flange отсутствует, pending flags
false. Calls terminal/own fixture closed, baseline пуст/free. Source digest
`cedd0bf719336bbe6e91cab0c63c81a13a9d7b5cb4f5e1265e4804c514a8c3a6`.

Anonymous plane не имеет пригодного native PID и не является edit target.
Её геометрия доказывается exact owning sketch, всей сетью canonical point/segment
references, explicit source projection и полным жёстким transform. Closing
проверяет kind/non-null и весь transform, без сравнения transient plane interfaces.
Named-plane reader не ослаблен. **380 связанных pure passed**; native этой финальной
правки, partial restoration, домен/MCP и итоговый installed wheel ещё нужны.

Source22 уточнила конкретный disconnect: `pattern_edge_points(receipt.edge)` →
`curve.IsLine()` старого pre-insertion дескриптора, до factory. Receipt: sketch и
driver возвращены, profile_before ещё не доказан, flange отсутствует; pending
creation/deletion false. Unknown сохранён, все calls terminal, own fixture closed.

Исходные finite line endpoints теперь фиксируются до записи в receipt; после own
insertion старую кривую не читаем. Сохранённый descriptor связывается с current
edge PID/geometry и полным current source/body/topology proof. Для AddEdges берётся
свежее проверенное ребро; client reference не обновляется. **379 связанных pure
passed**, включая disposed-curve case и отказы отсутствующего/неверного исходного
descriptor. Native этого исправления ещё не завершён; MCP/wheel по-прежнему нет.

Source21 с ограниченной source-edge привязкой также не принята: COM disconnect
`RPC_E_DISCONNECTED` до подтверждённого результата. Job unknown сохранён,
all_calls_terminal/fixtures_closed true. Следующий диагностический прогон
сохраняет traceback и receipt phase в приватном work, чтобы установить конкретный
устаревший native объект; production binding вслепую не ослабляется.

Source20 с новым reader отклонена до factory: после создания own input sketch
resolver исходного edge PID вернул другой COM interface, строгий pre-write edge
check не прошёл. Job unknown сохранён; all_calls_terminal/fixtures_closed true,
baseline пуст/free. Этот результат не засчитывается приёмке.

Добавлен отдельный source capture только для exact fully-defined closed own
pre-factory sketch. Исходный клиентский edge reference не обновляется. Проверяются
retained/current PID equality, оба полных line descriptors, unique current body
topology/owner, весь original L BREP, полный original feature census с единственным
новым own sketch, параметры и controls. До первого CAD-write старый строгий check
сохраняется. **376 связанных pure passed**,18 новых случаев source views. Native
нового кода ещё требует проверки; MCP/wheel не опубликованы.

В исходники добавлены dedicated `EdgeFlangeSketchReader` и полный native profile
readback. Они проверяют четыре user points, четыре линии и единственный own
internal projection, пять relations, жёсткий model-to-sketch transform, strong
entity references и точный SI/native identity управляющего размера. До factory
projection definition связывается с явным CAD-ребром; после — с own internal
segment. Полное имя размера может измениться, его native identity — нет.
**358 связанных pure passed**, включая reader/bridge и общие linear/circular
регрессии. Новый код подключён к create/naming/completed restoration; его native
приёмка ещё не завершена, доменный writer/MCP/wheel ещё не готовы.

Source18/19 (digest `440551a90a45ed71b951928d33abd2ca7d3ba899dc64bafcdb0a4d8ea30cf077`)
уточнили getter semantics до добавления reader: automatic plane PID Invalid=1,
COM plane view меняется при factory; exact driver identity сохраняется, полное
имя эскиза меняется. Projection definition до factory — CAD edge с native PID,
после — own ghost segment. Все вызовы terminal, контрольные детали закрыты,
полное original L восстановлено. Эти диагностические отчёты не принимают новый
reader и не превращают invalid plane PID в публичную ссылку.

Read-only domain preparation реализована в исходниках,26 новых pure-тестов;
связанный geometry/bridge/prepare/source-parameters/ownership/restoration набор
**224 passed**, включая21 тест проверки COM views и closing-проверки.
Полного pure нового кандидата и installed-wheel приёмки нет.
Новые tools не зарегистрированы; availability остаётся false до полного writer.

Source14 установила реальную связь derived UiBend: owner — exact FlatPattern,
sole parent — own OneBend, children отсутствуют. Он виден в complete feature
census и не перечисляется direct/fold-folder subfeature views. Подтверждены
U-форма и native параметры/GCS; observational jobs succeeded, fixtures closed,
baseline restored. Предположение о расположении внутри fold folder удалено.

Source15 выявила различие COM objects retained/current у прежних flat nodes.
Операция остановилась на census до naming/deletion; unknown сохранился,
вызовы terminal и контроль закрыт. Нельзя признать эти views равными только
по одинаковым ID/type/name. Далее — native PID equality/roundtrip плюс полные
descriptor/owner proofs.

Source16 подтвердила alternate views прежнего flat-семейства: native PID equality
и roundtrip обычных FlatPattern/ProfileFeature/UiBend возвращают точный retained
canonical объект, полные descriptors совпадают. Для FoldUpDownSketchFolder PID
не возвращает ни retained, ни текущий view, поэтому применяется только ранее
реализованная стратегия точного absorption через independently PID-bound owner.
Не используются ID/name-only aliases или межоперационный alias cache. Добавленная
привязка применяется к complete census, body membership, naming и completed restore;
повторно проверяет PID/descriptor/owner на closing boundary. Source16 observational,
не проверяет новый код привязки.

Source17 проверила production bridge с новой привязкой: full U BREP, оба native
allowance/параметры, GCS3, исходные элементы, русские имена новых узлов и getter
имени тела подтверждены. Затем exact own EdgeFlange удалён с absorbed-only flag,
полное исходное L-состояние проверено доменным capture/transition. Все четыре
jobs succeeded, all_calls_terminal/fixtures_closed true, failure null; baseline
пуст/free восстановлен. Source digest
`440551a90a45ed71b951928d33abd2ca7d3ba899dc64bafcdb0a4d8ea30cf077`.
Это source native-проверка bridge/completed restoration, без установленного wheel
и без нового MCP. Общий LinearSketchReader отклонил автоматическую плоскость;
полный специальный reader/profile evidence и partial restoration ещё нужны.

Блок 2.2 в работе. Установленный принятый пакет остаётся dev63, каталог44/15.
Новые MCP-инструменты отбортовки ещё не подключены; installed-wheel приёмки нет.

Контрольный инженерный сценарий: явно выбранное полное наружное продольное
ребро со стороны внутренней грани свободного конца вертикальной полки L-профиля → внутренняя отбортовка90°
с заданной длиной, радиусом и пользовательским K → двухсгибный U-профиль.
Длина задаётся от наружной виртуальной острой кромки, положение материала —
внутри. Толщина и исходный сгиб/эскиз наследуются от доказанной исходной детали.
Новые узлы должны получать русские имена; библиотечные обозначения сохраняются.

Подготовлен `EdgeFlangeOnL`: независимая полная BREP со всеми24 вершинами,
44 рёбрами и22 гранями, восемью конечными дугами и четырьмя цилиндрическими
поверхностями. Оба радиуса и оба K явные; проверяются запас прямых участков,
масса/площадь и прогноз нейтральной длины. Последний не является native-развёрткой.
Общий analytical reader маршрутизирует эту топологию в полный finite-arc reader;
census только выбирает reader и не доказывает форму.

Проверка выбранного ребра различает стороны свободной кромки и отклоняет
поперечные, частичные рёбра и швы сгиба. Для U-сценария выбирается внутренняя
сторона; противоположная сторона задаёт другое направление. Координаты не
заменяют владение: будущая доменная операция обязана
разрешить явный opaque edge_id, native persistent-ссылку и её принадлежность
доказанному текущему телу в указанном документе/конфигурации.

Ревизия связывает полную исходную форму, размеры, членов модели, опции
template/allowance/relief/gauge, native-ссылку ребра, параметры нового эффекта
и controls. Только дублирующие tolerance-checked native volume/area исключаются
из точного хеша. Их независимая проверка сохраняется.

Связанный pure-набор: **91 passed**, включая49 новых сценариев. Это искусственные
доказательства геометрии и ревизии, не CAD-приёмка. Полный pure-набор нового
инженерного кандидата пока не запускался; wheel не собирался.

## Source-пробы

Все материалы и CAD-журналы находятся в private work/ и не публикуются в Git.

1. Probe1: stale до CAD-записи из-за ошибочного включения дублирующей массы
   в experimental revision. Mutation checkpoint отсутствовал, своя деталь закрыта.
   Хеш исправлен и покрыт регрессией, исходный отчёт сохранён.
2. Probe2: штатный связанный эскиз создан, `AddEdges` с Python tuples вернул
   код1 `swEdgeFlangeError_EdgeNotSpecified`. До `CreateFeature` не дошло.
   Experimental restoration ещё не реализована, поэтому журнал остался unknown;
   он не переобъявлен успехом. После terminal-вызовов своя контрольная модель
   закрыта по постоянному разрешению пользователя, baseline пуст/free.
3. Probe3: явные `SAFEARRAY(DISPATCH)` дали AddEdges code0. Native EdgeFlange
   с r2,5/K0,38 создана; полная BREP прочитана. Направление оказалось наружным,
   поэтому U-prediction mismatch сохранён. Census24/44/22, V4092,6105674500086 мм³
   и A4485,451271946679 мм² совпали с U-прогнозом, но полная форма его отклонила.
   Это успешное observational-задание, не приёмка требуемой U-операции.
   Все вызовы terminal, своя модель закрыта. Getter входного sketch дал status2;
   принадлежность фактического absorbed sketch ещё исследуется.
4. Probe4: FlipDir эскиза при ReverseOffset=False дал то же наружное направление.
   Подтверждены фактические дети EdgeFlange: тот же входной ProfileFeature и
   новый OneBend. Идентичность sketch сохранена, имя factory изменил автоматически.
5. Probe5: входной эскиз полностью определён совпадениями стыков,
   горизонтальной/вертикальными связями и размером высоты; ReverseOffset=True
   с прежним профилем не дал второго сгиба. Возвращённый объект и ForceRebuild3
   не являются доказательством эффекта. Полная форма осталась L.
6. Probe6: отрицательный профиль также не дал U; API изменил OffsetDistance до
   4,5 мм. Код самой Feature при этом0. Даже нулевой код не заменяет native
   readback параметров и полную ожидаемую форму.
7. Probe7: выбор внутреннего свободного ребра с ReverseOffset=False создал U,
   эскиз fully-defined до и после factory, Feature error0. Но высота профиля15 мм
   отсчитывалась от внутреннего ребра, а наружная длина стала17 мм; U-предикат
   это отклонил. Предыдущие несовпадения не переобъявлены успехом.
8. **Probe8 подтверждена:** профиль высотой13 мм от внутреннего ребра дал
   наружную виртуальную длину15 мм, native OffsetDistance≈0,015 м, r2,5/K0,38.
   Вся U-BREP24/44/22 совпала с независимым прогнозом, эскиз status3 до/после
   factory, AddEdges0/Feature error0. V4092,6105674500104 мм³,
   A4485,4512719466775 мм². После полной формы и PID/absorption-проверок
   фактические ProfileFeature/OneBend получили русские имена, имя списка
   вырезов подтверждено в финальном дереве. Тело переименовано в исходное
   имя; отдельный readback имени тела ещё нужен в production postconditions.
   Все три задания succeeded/committed, свои документы закрыты, baseline
   пуст/free, native-вызовы terminal. Source digest
   `91468e034faa3f63ca69dc07bb697380d454457f37b15fb7700476ec0a481032`.
   Это source-проверка primitive, а не приёмка wheel/MCP или всего пункта2.2.

Основные первичные источники — установленная справка SOLIDWORKS2023:
`IEdgeFlangeFeatureData`, `AddEdges`, `InsertSketchForEdgeFlange`,
`swEdgeFlangeError_e`, `swFlangeDimTypes_e`, `swFlangePositionTypes_e`.
Предпочтительный factory-путь `CreateDefinition`/`CreateFeature` подтверждён в
[справке API](https://help.solidworks.com/2024/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEdgeFlangeFeatureData.html).

## Что требуется для завершения блока

### Native bridge в исходниках

Добавлен внутренний `CadSheetEdgeFlangeMixin`, без регистрации новых MCP-tools.
Он использует подтверждённую factory-сигнатуру и профиль высотой F−t,
сохраняет отдельные native-ссылки edge/sketch/flange/OneBend/UiBend и проверяет
всё expanded membership. Original base/sheet/template, relief/gauge и первый
K читаются независимо и должны совпасть с receipt до записи новых имён.
После полной U-формы проверяются русские имена, включая новый UiBend,
и фактическое имя тела. Canonical COM identity сравнивается по равенству,
без хеширования; оба порядка концов converted line поддерживаются.

Подготовлен `restore_completed_sheet_flange`: удаление только собственной
законченной отбортовки с absorbed nodes, без generic Undo и удаления
зависимых элементов. Проверяется возврат всей L-формы, baseline membership,
параметров и имён. Частичный sketch и неопределённый native factory этим
методом не очищаются; для них ещё нужен отдельный доменный путь восстановления.
Это реализация в исходниках, пока без подтверждённой native-приёмки этого пути.

Связанные проверки bridge/geometry/options/ownership/restoration:
**170 passed**, искусственные COM/геометрические сценарии.
Source-probe9 остановилась до создания sketch из-за хеширования PyIUnknown;
source-probe10 остановилась после конвертации ребра из-за ошибочного требования
положительного порядка концов. Обе ошибки исправлены и покрыты регрессиями.
Private experimental restoration в этих пробах не подтверждена, журналы
сохранили unknown; все native-вызовы завершены, свои документы закрыты,
baseline пуст/free. Эти отказы не считаются успешной CAD-приёмкой.
Source-probe11 прошла проверки requested flange parameters, всей U-BREP
и fully-defined absorbed sketch, затем отклонила ожидаемую flat absorption:
`sheet_flange_flat_membership`. Имена ещё не менялись, удаление отбортовки
не запускалось. Experimental restoration отсутствует, job остался unknown;
вызовы terminal, своя модель закрыта, baseline пуст/free. Native bridge целиком
и completed-U restoration не приняты. Требуется наблюдение фактической
flat-структуры и persistent/identity readback; census/native ID не заменяют
принадлежность. В диагностике теперь сохраняются фактические и retained ID/type,
чтобы дальнейшая проверка дала конкретное расхождение.
Полный source digest и private journal сохранены в отчёте work/.
Dev63/wheel/catalog44/15 остаются прежними.

- Примитив внутренней отбортовки и полная native U-форма подтверждены source-probe8.
  Перенести проверку точных параметров и fully-defined сети эскиза в domain/backend.
- Реализовать receipt владения новым bundle, сохранение исходных узлов/параметров
  и русские имена фактически созданных элементов, включая служебные сгибы.
- Реализовать доменную мутацию по документу/конфигурации/base/edge/revision/request_id:
  checkpoint, guard, postconditions, безопасное восстановление известного сбоя.
- Подключить MCP-фасад, выполнить полный pure-набор и приёмку точного установленного
  wheel, включая отказы до записи и пользовательскую цепочку. Развёртка U-профиля
  также требует расширения нынешнего L-only контракта и отдельной native-проверки.

Весь пункт2.2 и стадии PLAN.md остаются открытыми. Импорт/экспорт отложены.


Dev64 terminal-аудит подтвердил совпадение исходного эскиза и strong members,
различаются только5 original:relation: wrappers. Full L сохранён; свои документы
закрыты, empty/free baseline восстановлен, unknown-журнал не изменён.
**Dev65:3872 pure passed /323 CAD deselected (47,30с)** перед сборкой.
Installed-wheel/native приёмка dev65 ещё не выполнена.
