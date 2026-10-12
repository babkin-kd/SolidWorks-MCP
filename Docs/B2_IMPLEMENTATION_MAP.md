# Конечный остаток B2: правки и собственный конечный элемент

Read-only обзор после source/installed dev93; фактическая native-приёмка B1 ещё
выполняется. Этот документ не расширяет блок и не объявляет новые инструменты
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
3. Own suppress→unsuppress возвращает exact geometry/history. **Блокер resolver:**
   `CadGeometryMixin.resolve_persistent_id` сейчас отвергает suppressed status;
   unsuppress нельзя реализовать простым повторным использованием этого reader
   или поиском по имени. Нужен отдельный ограниченный путь same suppressed PID/
   canonical incarnation с complete membership и независимо проверенной целью.
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
