# Расстояние от экземпляра детали до бесконечной оси

Кандидат dev77; native-приёмка ожидается. Единственный новый инструмент:
`measurement_get_component_axis_distance`, операция read
`measurement.component_axis_distance`, scope `resolved_part_component_axis_distance_v1`.

Явно передаются root assembly document_id, активная configuration,
expected_observation_revision, component_id, request_id. `axis_origin_mm` —
конечная тройка в мм, `axis_direction` — конечный ненулевой вектор, который
нормализуется без переполнения/потери малых чисел. Необязательный `frame` —
правые ортонормальные оси и начало в root assembly; без scale/shear/reflection.
Ось — бесконечная прямая, а не конечный отрезок от переданного начала.

Для всех normal solid тел точного resolved part instance native GetExtremePoint
вычисляет две directional supports в local coordinates; total instance transform
переносит их в root assembly. Они задают конечный интервал проекций всех точек
тел на ось. Ближайшая точка бесконечной оси является ортогональной проекцией
ближайшей точки тела и лежит в этом интервале. Конечное временное ребро,
охватывающее интервал с положительным запасом, поэтому сохраняет минимум.
Approximate bounding box не используется для определения длины ребра.

IModeler.CreateLine → ICurve.CreateTrimmedCurve2 → CreateWireBody создают
temporary wire в памяти owning STA; тип, линейность, единственное ребро и
его native вершины проверяются. IModelDoc2.ClosestDistance получает точный
component и это ребро. Нет вставки в модель, эскиза, выбора, display, активации,
rebuild или удаления элементов. Все COM-прокси освобождаются на STA.

Результат: distance_mm, closest_points_mm в входной frame,
closest_points_assembly_mm в root assembly, normalized axes в обеих системах,
solid_body_count, infinite_line semantics. Проверяются finite native scalar,
norm двух witnesses, принадлежность axis witness прямой и support interval,
ортогональность пары. Closing gate повторяет полные body membership/summary,
solid moments, scalar directional supports, root/config/instance census и
total transforms. Равнозначный выбор extreme vertex не считается изменением,
сравниваются scalar projections (abs1e-9 м/rel1e-10), а не имена/XYZ вершины.
Это scoped read snapshot, не полная BREP mutation revision.

Скрытые твёрдые тела включены; surfaces исключены. Нулевой минимум сам по себе
не классифицирует interference/penetration. Aggregate subassembly, named native
frames, unresolved/lightweight/suppressed/SpeedPak, meshes и assembly-cut user
bodies остаются неподдержанными; нет автоматического разрешения/активации.
Тайм-аут ожидания не отменяет COM, request replay не запускает второй solver.

Документация SOLIDWORKS: [IsTemporaryBody](https://help.solidworks.com/2025/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IBody2~IsTemporaryBody.html),
[тип wire body](https://help.solidworks.com/2024/English/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swBodyType_e.html?format=P&value=),
[ClosestDistance](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~ClosestDistance.html),
[CreateTrimmedCurve2](https://help.solidworks.com/2019/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ICurve~CreateTrimmedCurve2.html).
