# Точка и бесконечная ось для агрегата компонентов

Dev79 принят в ограниченной области:4409 pure/323 CAD deselected,
installed metadata65/18, internal native24/public MCP8 на одном exact wheel.
[Приёмка](COMPONENT_AGGREGATE_PROBES_ACCEPTANCE.md). Реализованы
`measurement_get_component_aggregate_point_distance` и
`measurement_get_component_aggregate_axis_distance`, readonly operations
`measurement.component_aggregate_point_distance` / `measurement.component_aggregate_axis_distance`.
Scopes: `resolved_component_aggregate_point_distance_v1` /
`resolved_component_aggregate_axis_distance_v1`.

Явные root assembly/document_id, активная configuration, observation_revision,
component_id и request_id. Component может быть part или subassembly. Нормальная
native parent hierarchy определяет полный набор leaves, включая hidden; normal
solid/surface/empty rosters и canonical ownership проверяются на обеих границах.
Неподдерживаемые native states и named frames не включены. Нет implicit
resolution/activation/rebuild/selection/new CAD-tree entities. Units мм.

Point input и ближайшая точка находятся в root или explicit rigid frame.
Минимум берётся по **всем индивидуальным solid boundaries**, включая hidden
bodies и internal boundaries перекрывающихся частей; Boolean union не строится.
Все trimmed faces проходят IFace2.GetClosestPointOn; все тела классифицируются
native rays. Inside имеет приоритет, когда хотя бы одно тело содержит точку;
затем boundary, затем outside. Внутреннее расстояние остаётся положительным,
boundary tolerance0,00001мм даёт inside=null. Ambiguous rays отвергают весь read.
Возвращаются исходный nearest_component/body/face IDs, все body_locations с
component_id и полный face_count. Minimum не прекращается после нуля.

Axis input — origin_mm/конечный ненулевой direction, направление нормализуется;
explicit frame преобразует обе величины в root. Для каждого solid leaf exact
GetExtremePoint supports задают сертификат конечного temporary wire edge для
бесконечной прямой. Каждый leaf измеряется native ClosestDistance; zero не
классифицирует interference. Returns обоих witnesses/root+input frame и
исходного ближайшего component_id. Временное ребро существует только в памяти.

Оба результата содержат leaf IDs/count, solid leaf/body counts, excluded
nonsolid count и evaluated leaf count. Nonsolid leaves не входят в минимум,
но входят в complete closing body census. All body membership/summary/moments
и root hierarchy/config/model identities/transforms закрываются после всех
solvers; point также закрывает все face rosters/summaries, axis — supports.
Scope остаётся observation read, не полной BREP mutation revision.

Ограничения1000 leaves/5000 normal bodies/100000 solid faces. Для point весь
face census готовится до первого closest-point/ray solver. Никаких sampled/
approximate/partial results при превышении. Body/face reference budgets
каталога сохраняются отдельно. Scaling1000+ пока требует приёмки.

Подробные native24/public8 выполнены на одном installed wheel: две повторные
подсборки, nested hidden cylinder, positive inside/boundary, explicit frame,
native configuration replacement, multibody3/2, stale/foreign/inactive,
surface-only отказ, request replay. Два part regression cases проверили общие
point/axis helpers. Собственные модели/отчёты остаются вне публичного Git.
Исторические dev76/dev77/dev78 не засчитываются новым dev79 доказательством.
