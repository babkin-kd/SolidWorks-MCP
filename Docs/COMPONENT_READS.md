# Пассивная адресация экземпляров сборки

Scope `resolved_assembly_instance_reads_v1`: `component_list`, `component_get`,
`component_body_list`, `component_body_get`. Явные document_id, активная
конфигурация сборки, expected_observation_revision, request_id; никакого
переключения/resolve/rebuild/выделения. Наблюдение не является ревизией записи.

Каждый экземпляр имеет opaque component_id, native persistent reference в
корневой сборке и удерживаемую canonical identity. Один файл может повторяться
с разными referenced configurations/transform. Имена/пути — метаданные,
не ключи выбора. Отдельно проверяются native parent и полный путь вложенности,
инкарнации сборочной и referenced конфигураций, referenced model и состав.
Ссылки с другой конфигурацией/документом, заменённые и удалённые объекты не
перепривязываются. После rename старый ID разрешается по исходной native ссылке;
новая enumeration может выдать alias, если native представление PID изменилось.

Весь resolved native состав, метаданные и transform читаются дважды;
pagination сверяет полный snapshot каждой страницы, включая изменения без
document stamp. Бюджет100000 компонентов/удерживаемых записей pagination,
до100 курсоров. Это ограничение ресурсов, а не приёмка скорости сборок1000+.
Suppressed/lightweight/SpeedPak отклоняют весь scoped read. Автоматической
загрузки/разрешения нет; чтение таких состояний остаётся требованием стадии1.

Transform: `p_assembly_mm = origin_mm + Σ axes_in_assembly[i] * p_component_mm[i]`.
Он берётся из `GetTotalTransform(False)`, исключает presentation/exploded display,
относится к root active assembly. Ортонормальные axes, scale1; parity явно
указывает правую систему либо отражение. Принимаются только finite значения.

Тела получаются именно из `IComponent2.GetBodies3(-1)`, а не из текущей
конфигурации общего открытого part document. Поддержаны normal native
solid/surface, включая скрытые, до500 на один part instance. Body reference
получается/разрешается в корневой сборке; тело привязано к исходному component_id,
referenced configuration и текущему составу, повторно сверяемому после чтения.
Нельзя передавать его ID в geometry_get/part-измерения или другому экземпляру.
`component_body_get` возвращает одноэлементный `items`; body_list не имеет курсоров.

Координаты body `bounding_box_mm` остаются **component_model**. Они
приблизительные native GetBodyBox, не точные габариты сборки. Transform выдаётся
отдельно; axis-aligned box после поворота не становится точным geometric bound.
Normal component face/edge catalog принят отдельным dev74 scope:
[контракт](COMPONENT_TOPOLOGY.md), [приёмка](COMPONENT_TOPOLOGY_ACCEPTANCE.md).
Assembly-cut user bodies, mesh, subassembly-wide bodies, расстояния и измерения
сборки требуют следующих блоков/приёмки.

Primary API references:
[GetBodies3](https://help.solidworks.com/2018/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IComponent2~GetBodies3.html),
[Transform2](https://help.solidworks.com/2018/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IComponent2~Transform2.html),
[GetTotalTransform](https://help.solidworks.com/2018/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IComponent2~GetTotalTransform.html),
[Name2](https://help.solidworks.com/2022/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IComponent2~Name2.html).
