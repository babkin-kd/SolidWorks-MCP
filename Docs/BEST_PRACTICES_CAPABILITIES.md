# Матрица исполнимости лучших практик

Дата оценки: 11.10.2026. Статус документа: **draft**. Машинная версия:
[capabilities.json](../engineering/practices/capabilities.json).

Оценка связывает 12 карточек версии 1.0.0 с публичным каталогом исходников
`506e50617489d7ed233393f246dc0706987b7bfc`. Регистрация проверена в
[server_v2.py](../src/solidworks_mcp/server_v2.py) и подключённых MCP-фасадах.
В момент оценки рабочие изменения пакета `src/solidworks_mcp` отсутствовали.
Отдельно без CAD прочитана установленная metadata dev87: build commit
`6437b337b01300a73c3b97a7604c2fb5cad58729`, clean, digest
`ec4e6a56d215a6d3e37b447cc4125635ebd05e495b3fdc16f940fcd50f97caa2`.
Это чтение metadata, а не новая проверка установленного каталога или native-приёмка.

Официальные исходные рекомендации подтверждают происхождение методики. Они
не подтверждают реализацию MCP, совместимость COM с установленной версией или
поведение нашего wheel. Внутренние алгоритмы и upstream-примеры не включаются
в публичную поддержку без регистрации и отдельной приёмки.

`partial` означает наличие отдельных поддерживающих операций. Полный сценарий
карточки этим статусом не подтверждается. `guidance_only` означает выбор
методики в инструкции для навыка без соответствующего серверного алгоритма.
`unsupported` означает отсутствие определяющей операции или её проверки;
перечисленные чтения дают только контекст. Статусы lifecycle/verification
карточек сохраняются; `native_accepted` не назначается.

## Детали — стадия 2.1

| Карточка | Статус | Реализованные чтения | Реализованные записи, относящиеся к теме | Недостающая часть |
| --- | --- | --- | --- | --- |
| [SW-PART-001](practices/SW-PART-001.md): размерная схема | partial | `system_get_info`, `feature_list`, `dimension_list`, `dimension_get`, `sketch_get`; подготовка размеров | `sketch_set_dimension`, `dimension_set_value`, `part_set_hole_dimension` в отдельных scopes | Создание выбранных зависимостей и изменение ширины уже просверленной детали |
| [SW-PART-002](practices/SW-PART-002.md): постоянные отступы | partial | `document_list_templates`, `feature_list`; парные подготовки основания, отверстия, массива и file lifecycle | `document_create_part`, `part_create_base_extrusion`, `part_create_through_hole`, `part_create_linear_hole_pattern`; ограниченные save/close/open | Native-зависимость от W, редактирование основания с парой, полный persistence-сценарий, первое сохранение новой детали |
| [SW-PART-003](practices/SW-PART-003.md): постоянный шаг и центрирование | partial | `feature_list`, `edge_list`, `dimension_list`, `part_prepare_through_hole`, `part_prepare_linear_hole_pattern` | `part_create_through_hole`, `part_create_linear_hole_pattern` | Центрирование от W и изменение размеров после массива |
| [SW-PART-004](practices/SW-PART-004.md): базирование эскиза | partial | `feature_list`, `feature_get`, `sketch_get`, `part_prepare_base_extrusion`, `sketch_prepare_dimension_change` | `part_create_base_extrusion`, `sketch_set_dimension` | Произвольные базы/плоскости и позиционные связи; поддержан только ограниченный профиль с углом в начале |
| [SW-PART-005](practices/SW-PART-005.md): простые связанные эскизы | partial | `sketch_get`, `dimension_list`, `dimension_get`; ограниченные подготовки основания/отверстия | `part_create_base_extrusion`, `sketch_set_dimension`; фиксированная сеть связей созданного основания | Общий редактор отношений, симметрия/равенство и произвольные криволинейные/внешние сети |
| [SW-PART-006](practices/SW-PART-006.md): роль скругления | partial | `feature_list`, `feature_get`, `body_list`, `edge_list`, `geometry_get`, `part_prepare_edge_fillet` | `part_create_edge_fillet` | Цепочка скругление → зависимая бобышка, редактирование радиуса и порядка |
| [SW-PART-007](practices/SW-PART-007.md): выбор инструмента | guidance_only | `system_get_info`, `feature_list`, `feature_get`; prepare выбранного ограниченного элемента | Базовое вытягивание/вращение, угловой вырез, отверстие, линейный массив, одно скругление | Серверный выбор/сравнение по замыслу; Shell и Rib отсутствуют |
| [SW-PART-008](practices/SW-PART-008.md): зависимости и порядок | partial | `feature_list`, `feature_get`, `geometry_get`, `dimension_list`, `dimension_get`, `sketch_get`, `job_get`, `job_list` | Общая запись порядка и зависимых элементов отсутствует | Публичный полный граф зависимостей, перестановка и guarded-изменение родителей |

Точные имена всех связанных prepare/execute-инструментов и ссылки на их исходники
перечислены для каждой карточки в JSON. Здесь представлены существенные чтения
и записи; такая группировка не разрешает последовательное применение инструментов
к произвольному общему телу.

Ограничения, существенные для выбора метода:

- [SKETCHES.md](SKETCHES.md): `sketch_get` читает поддержанный линейный плоский
  эскиз, его определённость и отношения. Он отклоняет кривые и неподдержанные
  внешние сущности. `sketch_prepare_dimension_change` → `sketch_set_dimension`
  меняет W/H полностью определённой прямоугольной базы в своём исходном scope.
- [PART_HOLE.md](PART_HOLE.md) и [PART_HOLE_EDIT.md](PART_HOLE_EDIT.md):
  `part_prepare_through_hole` → `part_create_through_hole` создаёт одно отверстие
  с независимыми X/Y/диаметром; редактор
  `part_prepare_hole_dimension_change` → `part_set_hole_dimension` меняет один
  из этих параметров. Область не разрешает изменение основания после отверстия
  или добавление второго отверстия тем же одиночным инструментом. Окружность
  читается внутренними captures парных подготовок, а не через `sketch_get`.
- [PART_PATTERN.md](PART_PATTERN.md):
  `part_prepare_linear_hole_pattern` → `part_create_linear_hole_pattern` создаёт
  один LPattern вдоль положительного X/Y, 2–64 экземпляра с постоянным шагом.
  Это даёт физическую пару, но не зависимость постоянных отступов или центрирования
  от W. Дальнейшее редактирование массива/отверстия/основания исключено.
- [PART_FILLET.md](PART_FILLET.md):
  `part_prepare_edge_fillet` → `part_create_edge_fillet` создаёт одно скругление
  полного ребра обычного кубоида. Создание зависимой бобышки, редактирование
  скруглённого тела, множество скруглений и перенос на касательные грани исключены.
- [dimension_tools_v2.py](../src/solidworks_mcp/dimension_tools_v2.py):
  `dimension_set_value` меняет допустимый независимый размер элемента и отклоняет
  размеры эскиза, driven/linked/equation и неподдержанные dependency-контексты.
  Его наличие не даёт редактор уравнений или общую правку параметров всех моделей.
- [API_V2.md](API_V2.md): внутренние `feature.dependencies` и dependency context
  имеют исторические результаты, но не зарегистрированы как публичные инструменты.
  `feature_list` показывает дерево, а не полный граф родителей/потомков или preview
  последствий удаления/перестановки.
- [NATIVE_DOCUMENT_SAVE.md](NATIVE_DOCUMENT_SAVE.md):
  `document_prepare_save_native` → `document_save_native` сохраняет существующий
  bound-файл. Первое сохранение unsaved-модели отсутствует в оценённом baseline.
  Save/close/open не подтверждают сохранение предлагаемой геометрической зависимости.

Пилот SW-PART-002 зависит от трёх самостоятельных условий: возможности
создать и прочитать native-зависимость от W; полного ревизионного scope для
изменения W уже после появления пары отверстий; lifecycle-цепочки первого
сохранения новой модели и повторного открытия с заново разрешёнными ссылками.
Полная shape-проверка должна учитывать исходное основание и обе цилиндрические
стенки, центры и контуры отверстий. Изменение W на пустом прямоугольном основании
через `sketch_set_dimension` не является редактированием просверленной пластины.
Совпадение двух начальных координат или создание LPattern с вручную рассчитанным
шагом не доказывает сохранение отступов при дальнейшем изменении W.

Реализация этих зависимостей следует пункту 2.1 и формальному переходу к стадии 2
в [основном плане](../PLAN.md). Наличие ограниченных исторических feature-сценариев
не закрывает незавершённые обязательные условия стадии 1.

## Сборки — стадия 2.6

| Карточка | Статус | Доступный пассивный контекст | Недостающая определяющая операция |
| --- | --- | --- | --- |
| [SW-ASSY-001](practices/SW-ASSY-001.md): степени свободы | unsupported | `document_get`, `component_list`, `component_get`, `component_body_list`, `component_body_get` | Чтение/создание сопряжений, DOF и проверка разрешённого движения |
| [SW-ASSY-002](practices/SW-ASSY-002.md): схема сопряжений | unsupported | `component_list`, `component_get`, `component_body_list`, `component_body_get`, `component_face_list`, `component_edge_list`, `component_topology_get` | Граф/создание сопряжений и проверка базирующей схемы |
| [SW-ASSY-003](practices/SW-ASSY-003.md): внешние зависимости | unsupported | `component_list`, `component_get`, `component_body_list`, `component_body_get`; `dimension_list/get` отдельной открытой детали | Создание внешних ссылок, назначение источника, полный анализ циклов и распространение параметров |
| [SW-ASSY-004](practices/SW-ASSY-004.md): жёсткость подсборки | unsupported | `document_get`, `component_list`, `component_get` | Режим rigid/flexible, переключение конфигураций и проверка внутреннего движения |

[COMPONENT_READS.md](COMPONENT_READS.md) и
[COMPONENT_TOPOLOGY.md](COMPONENT_TOPOLOGY.md) разрешают passive-чтения полностью
resolved экземпляров, их normal native тел и топологии. Конфигурация и transform
дают контекст конкретного экземпляра; они не доказывают степени свободы или
корректность сопряжений. Suppressed/lightweight/SpeedPak отклоняются; auto-resolve,
selection, переключение конфигурации и rebuild отсутствуют в этих чтениях.
Ссылки экземпляра не становятся целями отсутствующих assembly mutation-tools.

## Использование оценки

Навык должен проверять фактический каталог подключённого сервера и ограничения
каждого шага перед выполнением. Подготовка возвращает ревизию соответствующего
scope; наблюдательная ревизия не заменяет её. Для неизвестного исхода требуется
согласование состояния, а `job_get` отслеживает уже отправленное задание.

После реализации пилота обновляется только доказанная область матрицы. Native-
доказательства добавляются в карточки отдельно с точным wheel и окружением;
этот обзор исходников не заменяет принятие методики или CAD-операции.
