# Конечный остаток B2: правки и собственный конечный элемент

**Текущий source checkpoint (13.10.2026):** собственный suppression domain,
full retained DIM/annotation producer, executor, runtime и два MCP инструмента
реализованы. Связанные pure и полная приёмка wheel проверяются отдельно;
native/MCP B2 ещё не принят. Последний compatibility/intrinsics probe dev94
normal exit0,652,52 с, full baseline/own cleanup подтверждены. Точные границы
и исторические отказы — [сводка](B2_PID_COMPATIBILITY.md). Own-leaf preview/delete
остаётся отдельной задачей. Прежние записи ниже сохранены как история подготовки.

Исходный обзор выполнен после source/installed dev93; B1 впоследствии принят
на точном dev94: [сводка](B1_DEV94_ACCEPTANCE.md). Этот документ не расширяет блок и не объявляет новые инструменты
реализованными. Нормативные шесть условий: [приёмка B2](STAGE_1_BLOCK_ACCEPTANCE.md#s1-b2--размер-имя-подавление-и-удаление),
[матрица](STAGE_1_REQUIREMENTS_MATRIX.md). Новые маршруты не добавляются в
каталог до реализации; установка и COM остаются у одного владельца.

## Реализованная основа и фактические пробелы

| Область | Доказанная исходная основа | Остаток B2 |
| --- | --- | --- |
| Driving length | `DimensionCatalog.set_value/_writable`, paired captures, verify/restore; native typed setter/rebuild/readback; `dimension_list/get/set_value` | Итоговая same-wheel цепочка 10→12 мм/8000→9600 мм³ на профиле B1 и отказные gates |
| Русское имя | `FeatureCatalog.rename`, `CadFeaturesMixin.rename_feature`, PID независимо от имени, checkpoint/recheck/restore; `feature_rename` | Общая B2 приёмка с сохранением того же opaque ID/canonical/PID после rename |
| Dependency/context | `FeatureCatalog.dependencies/deletion_structure/deletion_context`; `FeatureGraphRead`, `structural_candidates`, `context_semantics/deletion_context` | Эти reads консервативно возвращают `deletion_authorized=False` и `deletion_impact_complete=False`; это не authorized preview/execute |
| Suppress/unsuppress | Узкий sheet-state и legacy вызовы не являются общим v2 контрактом | Exact own PID/canonical target/configuration, доказанный affected set, native setter/rebuild и полные before/after proofs |
| Preview/delete | Owned creation inverses имеют отдельные scopes; legacy name-selected cascade непригоден | Закрытый complete inventory, разрешение только доказанного собственного leaf, подготовленная revision, exact retired/survivor sets и независимый execute gate |

Основные файлы: `src/solidworks_mcp/dimensions.py`, `cad_dimensions.py`,
`features.py`, `cad_features.py`, `feature_dependency_graph.py`,
`feature_deletion_structure.py`, `feature_deletion_context.py`.
Соответствующие pure suites: dimension domain/rebuild/namespace/identity,
feature domain/revision/identity-close, dependency graph/deletion structure/
context/external-reference bindings.

## Конечные поддержанные случаи и инженерный результат

1. Управляющая длина основания 10→12 мм; фактический rebuild/readback и объём
   8000→9600 мм³. Explicit active part/configuration и strong dimension anchor.
   Linked/read-only/unsupported controls отклоняются до записи.
2. Русский rename/readback того же элемента; прежняя устойчивая ссылка
   продолжает разрешать exact feature без выбора по новому имени.
3. Own suppress→unsuppress возвращает exact geometry/history. Текущий generic
   resolver отвергает nonzero persistent state, а rename явно запрещает
   suppressed feature. **Native необходимость отдельного resolver доказана**:
   own suppressed extrusion возвращает state2 с raw exact canonical feature.
   Internal bridge реализован с original PID/retained identity/full membership;
   generic resolver не расширен. [Совместимость API cycle](B2_PID_COMPATIBILITY.md)
   не заменяет приёмку domain/MCP suppression. Подмена имени/GetID запрещена.
4. Preview остаётся read-only; execute удаляет лишь подтверждённый собственный
   конечный набор, сохраняет survivors и инвалидирует старый ID. Наличие
   structural candidates само по себе не разрешает удаление.
5. Dependency/linked/stale/replay отказы не дают повторной физической записи.
   Русское имя отображается, а не определяет идентичность.
6. Known scalar/create/delete failure требует no-effect или полного scoped
   восстановления; неполный эффект остаётся unknown/hold. Dirty сосед,
   конфигурации вне цели, selection/view, окна, файлы и настройки сохраняются.

**Scope не расширяется:** broad children/absorbed/equation cascades, произвольные
dependency graphs и новые типы features относятся к отдельным D2-задачам.
Базовое выдавливание не объявляется допустимым leaf автоматически: absorbed
sketch, dimensions, annotations и другие ссылки сначала входят в полный impact.
Неподдержанный или неполный impact запрещает запись.

## Порядок после завершения B1

1. Заморозить уже закрытый B1 scope и зафиксировать точный accepted wheel.
2. Выбрать конечный собственный leaf-case по полному inventory и реализовать
   отдельные suppression/preview/delete domain contracts с guards/checkpoint/
   paired native ledger/unknown/no-retry. Не превращать conservative blockers
   в authorization простым удалением флагов.
3. Добавить только реализованные runtime/MCP маршруты и связанное pure покрытие.
4. Один full pure → итоговый wheel → installed gate → обязательные internal
   native отказы/восстановление и public цепочка одного wheel. Разрушительные
   проверки выполняются на отдельной собственной fixture; повторы физических
   случаев между internal/public нужны только для отдельного свойства.
5. Закрыть B2 лишь по всем шести условиям, cleanup/baseline и фактическим P/I/N.

Обзор выполнялся без редактирования кода, запуска проверок или обращения к CAD.
Карта фиксирует следующий минимальный шаг, а не native-приёмку или новую оценку
готовности исторических wheel.

## Уточнение API перед реализацией suppression

Документация SW2023 [GetObjectByPersistReference3](https://help.solidworks.com/2023/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~GetObjectByPersistReference3.html)
ограничивает Suppressed/Deleted state flags топологическими объектами и поясняет
возврат базового feature object. [GetNextFeature](https://help.solidworks.com/2023/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeature~GetNextFeature.html)
позволяет перечислять suppressed features. Поэтому прежнее утверждение,
что suppression обязательно делает feature PID недоступным с state2,
заменено проверяемым предположением. Это уточнение плана, не native support.

[GetID](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeature~GetID.html)
стабилен для элемента документа и отличается от persistent reference.
Он остаётся дополнительным census/incarnation признаком, не fallback-адресацией.
После B1 короткий owned probe должен сохранить feature PID/canonical identity,
подтвердить действительное suppression состояние в явной конфигурации,
полный affected census и exact unsuppress возврат. Пропадание/новая инкарнация
тела или грани не даёт права присвоить старую ссылку новому объекту.

## Подготовленный receipt gate короткого probe — 13.10.2026

`verifier_b2_suppression_probe.py` проверяет фактические три упорядоченные фазы
before/suppressed/restored, исходный feature PID и canonical ordinal, normal
resolver state0, GetID и полную feature membership. Canonical ordinals producer
назначает по удерживаемым IUnknown equality; имя/GetID не заменяют PID.
Перед/после нужны полные existing rectangle snapshots и точный BREP/reference
return; suppressed phase требует actual empty geometry и complete feature tree.
Допустимый affected set — own base и только наблюдённый absorbed sketch.

Probe ограничен **двумя собственными dirty unsaved деталями**, одной
конфигурацией без refs; файлы и сохранённые соседи запрещены, не замалчиваются.
Сосед/window/session/preferences сохраняются, CommandInProgress — строго False
на фазовых captures вне нормально освобождённого setter/rebuild guard. Четыре
normal returned actions: SetSuppression2(0/2,1,None), ForceRebuild3(False).
Receipt validation не разрешает следующий native call/cleanup/process stop и
не принимает B2. Native producer и фактический probe после B1 ещё нужны.

Отдельные82 pure cases прошли2,65 с; общая интеграция новых B2/B3 файлов с
reader/journal/manifest — **200 passed /7,79 с**. New fixtures искусственные,
COM не вызывался; production/wheel текущей B1 приёмки не менялись.

Конкретный read-only producer `verifier_b2_probe_observer.py` формирует phase
receipt из root-owned retained bindings: canonical ordinal pool, actual raw
GetObjectByPersistReference3/status и обычный adapter resolver, полный census,
IsSuppressed2, geometry/full neighbor oracle и coherent session/preferences/
event watches. Configuration identity уже canonical IUnknown и не оборачивается
повторно. Producer не создаёт fixtures, не вызывает setter/rebuild, не выбирает
по имени, не закрывает документы и не разрешает dispatch. Native root-драйвер
короткого probe ещё требуется; normal creation/action receipts создаёт он.
Свои30 pure cases прошли0,89 с, три produced artificial phases прошли strict
receipt gate. Общая последующая интеграция observer/gate/B3 — **230 passed /8,89 с**;
результат перекрывает предыдущий200, не является дополнительными CAD случаями.

## Собственный native-драйвер короткого probe — 13.10.2026

`scripts/verify_b2_suppression_pid.py` подготовлен для последовательного запуска
единственным владельцем CAD. До подключения COM проверяются принятый dev94,
точный SHA wheel и итогового аудита B1, исходные native-отчёты и hashes helpers;
проверяется установленный пакет без исходников в `PYTHONPATH`. Повторного MCP
metadata-процесса нет. Пользовательские документы или занятый служебный флаг
запрещают создание контрольных деталей.

Две собственные детали привязываются к нормально возвращённым handles,
canonical identities и HWND до последующих записей. Каждый setter/rebuild
однократен, pending/returned записываются до/после вызова; ошибка запрещает
последующие изменения. Очистка следует только после нормального завершения
всех действий и проверки receipt. Retained-процесс при ошибке не завершается
по таймауту и не разрешает автоматического повтора.

Root-проверка driver/observer/gate: **139 passed /4,28 с**. Пассивный gate на
фактическом установленном dev94 прошёл. Native-запуск начат, результат ещё
не принят. Эти проверки не закрывают B2, не объявляют suppression/delete
реализованными инструментами и не меняют wheel, на котором принят B1.

Первый native probe завершился отказом read-only session gate до первого
setter, через145,33 с. Реальный part mode включает `drawing_state: null`;
искусственная fixture и gate ошибочно ожидали только пять остальных полей.
Gate исправлен с обязательным явным null, без допуска неизвестных полей;
добавлены отказы для отсутствующего/не-null/лишнего поля. Связанные проверки:
**143 passed /4,35 с**. Root отдельно подтвердил normally returned Python
validation failure, отсутствие setters, точные HWND/PID/metadata обеих
собственных деталей и освобождённые guards. Завершён только проверенный
простаивающий retained-worker; две контрольные детали закрыты без сохранения,
пустой исходный baseline/application/preferences подтверждены. Исторический
отказ не превращён в успешный probe. Следующий свежий запуск остаётся
проверкой совместимости, не приёмкой B2.

Второй probe: первый actual `SetSuppression2(0,1,None)` нормально вернул True;
перед rebuild generic installed resolver отверг исходный feature PID со state2.
Отказ131,26 с; rebuild/unsuppress не выполнены. Root независимым read-only
наблюдением подтвердил **raw state2 возвращает сам feature**, его canonical
IUnknown совпадает с единственным текущим членом полного census с исходным
PID; `IsSuppressed2` возвращает True, body census пуст. Pending actions нет,
guards освобождены. Own controls закрыты; исходный пустой baseline подтверждён.
Таким образом, необходимость поддержки suppressed feature PID доказана native,
а прежнее предположение normal state0 для всех фаз опровергнуто на SW2023 SP2.1.

Подготовлен **test-owner prototype**, не новый installed tool: status2 допустим
только с raw non-null feature, исходным PID, удерживаемой canonical identity,
уникальной текущей membership и фактическим suppression True. Null, иной raw
объект, combined/deleted states и выбор по имени/GetID запрещены. Generic
production resolver не изменён. Gate разрешает state2 только suppressed phase;
before/restored по-прежнему требуют state0. Связанные проверки prototype:
**161 passed /4,50 с**. Следующий probe проверит полный suppress/rebuild/
unsuppress/rebuild cycle; результат не заменяет приёмку инструментов B2.

В исходниках добавлен внутренний `resolve_retained_feature_pid`:
`retained_feature_resolution.py` и bridge в `CadGeometryMixin`. Он требует
удерживаемую native identity; generic resolver и public reference admission
остаются прежними. Source-only28 pure проверяют нормальный state0, exact state2,
null/foreign/duplicate membership, неверный PID и строгие native Boolean/state
types. Совместно с существующими plane/feature identity и независимыми B4
helpers — **236 passed /6,87 с**. В установленный dev94 этот код не входит;
новый wheel будет собран после доменной реализации и MCP-фасада B2.

Третий native probe выполнил все четыре setter/rebuild нормально и собрал
все три фазы, но exact restoration gate отказал через327,85 с. Полный diff
before/restored содержит **ровно одно отличие: `clone_state/body/name`**:
SolidWorks вернул имя операции вместо исходного имени тела. Геометрия,
ссылки и остальные поля full oracle совпали. Все guards освобождены,
pending вызовов нет. Root независимо подтвердил quiescence и ownership,
закрыл только две контрольные детали и проверил пустой исходный baseline.
Этот опыт подтверждает API cycle, но не exact restoration и не B2 acceptance.

`verifier_b2_body_name_restore.py` допускает коррекцию только после полного
независимого наблюдения delta, ограниченного own body/name; полный сосед,
session, feature canonical census и PID сохраняются. Перед единственной
записью проверяются текущие metadata, explicit document/configuration,
единственный current body с original PID и неизменённое наблюдённое имя.
Pending/returned/readback и освобождение guard записываются. Исходная фаза
с потерянным именем сохраняется отдельно; итоговая restored phase собирается
заново из CAD. Artificial integration/отказы: **181 passed /5,26 с**.
Следующий свежий probe проверит это обязательное постусловие; wheel94 неизменён.
