# Грани и рёбра конкретного экземпляра

Scope `resolved_assembly_instance_topology_reads_v1`: `component_face_list`,
`component_edge_list`, `component_topology_get`. Дополняет
[catalog экземпляров/тел](COMPONENT_READS.md). Явные root document_id, активная
конфигурация сборки, expected_observation_revision, component_id, body_id,
request_id. Object_id — opaque persistent reference face/edge исходного тела,
полученная и разрешаемая в корневой сборке. Нет выбора по имени/порядку.

Проверяются canonical instance/model/configuration identity, current body,
native owner GetBody и полный topology membership. Отсутствующий/чужой/
пересозданный object не перепривязывается. После rename PID разрешается через
исходную native ссылку; если native bytes изменились, новая enumeration может
выдать alias, не меняя владельца старой ссылки. Reference lifetime ограничен
открытой сессией процесса, документом, конфигурацией и инкарнацией объекта.

Полные instance/body/topology snapshots повторяются перед ответом. Cursor
привязан к document/configuration/instance/body/kind и полному snapshot;
изменённый snapshot отвергается и без смены document stamp. Enumeration order
не принимается за identity; сортировка opaque IDs служит только pagination.
Лимит страницы1–200, topology/reference/retained-snapshot budget100000,
до100 курсоров. Native proxies освобождаются на owner STA. Это бюджет,
не подтверждение производительности больших сборок.

Area — мм²; длина/начало/конец ребра — мм в **component_model**, включая
скрытые native тела/экземпляры. `component.transform` отдельно переводит
локальные координаты в root assembly, без presentation/exploded transform.
Start/end могут совпадать на полном круге. Не смешивать локальные точки
разных экземпляров при вычислении расстояния; этот каталог расстояний не
вычисляет. Проверяются finite native area/length/точки; площадь положительна,
длина неотрицательна. Необеспеченный native curve contract отвергается.

Все операции passive: без selection, auto loading/resolve/config switch,
rebuild или изменения модели. Наследованы ограничения полностью resolved
native instances и normal solid/surface bodies. Suppressed/lightweight/
SpeedPak/mesh/assembly-cut user bodies требуют дальнейшей поддержки/приёмки.
Observation и перечисленные summaries не являются полным BREP certificate
или mutation revision. Geometry/body IDs детали не принимаются как instance IDs.

Primary API: [GetCorrespondingEntity](https://help.solidworks.com/2025/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IComponent2~GetCorrespondingEntity.html),
[GetCurveParams2](https://help.solidworks.com/2010/english/api/sldworksapi/SolidWorks.interop.sldworks~SolidWorks.interop.sldworks.IEdge~GetCurveParams2.html).
Диагностически подтверждено, что traversal из GetBodies3 возвращает topology
в правильном instance context; GetCorrespondingEntity не нужен для part-index
fallback и не вызывается вместо проверки owner/current membership.
