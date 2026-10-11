# Расстояние от экземпляра детали до точки

Кандидат dev76: `measurement_get_component_point_distance` →
`measurement.component_point_distance`, passive read; каталог61 инструментов/
18 guarded операций. Проверки pure не заменяют приёмку exact installed wheel.

Вход: request_id, document_id корневой сборки, её активная configuration,
expected_observation_revision, component_id из component_list, point_mm.
Три конечных числовых координаты в мм; bool/строки не преобразуются. По
умолчанию point в root assembly_model. Optional frame: finite rigid
origin_mm/axes_in_model с правой ортонормированной системой; используется
тот же контракт, что у measurement_get_bounds. Point и nearest_mm выдаются
в запрошенной frame, root точки дополнительно возвращаются явно. Named
native frames остаются в плане, произвольные имена не ищутся.

Scope `resolved_part_component_point_distance_v1`: fully resolved native
part instance, normal solid тела, включая скрытые; surface тела исключены.
Подсборка как цель, mesh/SpeedPak/unresolved/assembly-cut user bodies
унаследовали отказы component/body scope. Во всём native assembly census
должны пройти resolved gates. Целевая деталь должна иметь хотя бы один solid.
Полное membership тел/граней ограничено500 телами/100000 solid faces.

Point переводится в component-local SI по обратной полной native transform;
результат учитывает rotation/shift/nested ancestry и native mirrored parity.
Перебираются все обрезанные solid faces через
[IFace2.GetClosestPointOn](https://help.solidworks.com/2025/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFace2~GetClosestPointOn.html),
с полным root persistent roundtrip/owner/body membership каждой грани.
Требуются пять конечных XYZ/UV значений. Возвращается минимальное расстояние
до **индивидуальных границ solid тел**, original nearest_body_id/nearest_face_id.
Равные минимумы могут иметь разные nearest points; индекс/имя не идентификатор.
nearest_face_id можно передать в component_topology_get с теми же целями.
Габарит не заменяет ближайшую точку. Внутри материала distance_mm остаётся
положительным; не объявляется расстоянием до объединённого внешнего оболочечного
контура перекрывающихся тел или collision clearance.

Point_location определяется для каждого solid и объединяется: inside имеет
приоритет над boundary, затем outside. Внутренность любого solid означает
inside=True. Outside всех тел: False. Boundary без inside: None. Допуск
границы1e-8 м/0.00001 мм указан в результате; boundary определяется по native
расстоянию до границы данного тела, остальные случаи проверяются лучами.

[IModelDocExtension.RayIntersections](https://help.solidworks.com/2026/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~RayIntersections.html)
для каждого solid пакетно получает три различных normalized направления,
три одинаковых component-local origins и explicit body array. Options5 —
NORMALS1|ENTRY_EXIT4, HitRadius0, Offset1e-8 м, HighPrecision=True. UNBLOCK
и UI selection не используются. Native query cache читается сразу на том
же STA через
[GetRayIntersectionsPoints](https://help.solidworks.com/2026/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDoc2~GetRayIntersectionsPoints.html).
Проверяются count≤100000, nine-value records, конечность, native body/ray
indices, flags, positive ray position и нулевой радиус. Нет-hit ray означает
outside. Ближайший ENTER — outside, EXIT — inside; три направления обязаны
согласоваться. Отсутствующие/конфликтующие flags, malformed evidence или
расхождение направлений дают отказ. Face-normal heuristic не используется.

Перед и после измерения проверяются root observation/config identity,
полные instance/body/face rosters, persistent/native identities, referenced
configurations, transforms, summaries и12-significant-digit geometric moments
каждого solid. Witness norm дополнительно проверяется после трансформации в
root мм. Ограниченные read snapshots не являются полной BREP mutation revision.
Журнал mutates=false; timeout ожидания не отменяет COM. Native ray cache —
результат вычисления; модель, выделение, виды и настройки не изменяются.

Приёмка: hidden rotated outside/inside/boundary, original nearest face roundtrip,
replay, явная frame/trimmed corner; internal дополнительно hidden multibody с
более близким excluded surface, nested root transform, цилиндр inside/outside,
полый цилиндр (void outside/material inside), stale/inactive/foreign/subassembly,
native referenced config change, replaced internal body/face reference отказ,
surface-only target. Все модели собственные; native setup не объявляет новые
публичные engineering operations. Exact4-owned cleanup и baseline обязательны.

Point-направление legacy measure_distance закрывается в указанной part-instance
области. Axis distance, aggregate subassembly targets, named frames, прочие
states и общие installed/native gates остаются в матрице стадии1.
