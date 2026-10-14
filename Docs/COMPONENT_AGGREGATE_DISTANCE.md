# Расстояние между агрегатами экземпляров

Dev78 принят на exact wheel: internal19/public MCP6, оба accepted=true.
[Точная приёмка](COMPONENT_AGGREGATE_DISTANCE_ACCEPTANCE.md). Инструмент
`measurement_get_component_aggregate_distance`, read операция
`measurement.component_aggregate_distance`, scope
`resolved_component_aggregate_distance_v1`.

Две явные цели part/subassembly в одном root assembly: document_id,
активная configuration, expected_observation_revision, component_a_id,
component_b_id и request_id. Цели должны быть различными; общий дочерний
экземпляр разрешён. Необязательная explicit rigid frame определяет координаты
обеих ближайших точек в мм; root assembly witnesses возвращаются отдельно.

Полный native census проверяет persistent references, canonical instance/
model/config identities, parent hierarchy и total transforms. Потомки
выбираются по проверенным parent_component_id, а не имени файла или bbox.
Все normal solid part leaves входят в минимум, включая скрытые экземпляры и
тела. Empty/surface-only leaves входят в census и closing gate, но исключены
из solid minimum. Цель без единого solid leaf отвергается.

Для каждой пары solid leaves IModelDoc2.ClosestDistance измеряет native
минимум с двумя root witnesses. Глобальный минимум берётся по всем парам,
без early-zero break, выборочного sampling или approximate bbox fallback.
Если leaf instance входит в обе цели, native GetExtremePoint подтверждает
точку одного normal solid, total transform даёт два одинаковых root witnesses
и точный ноль. Не выполняется недопустимый native self-distance вызов.
Этот ноль не классифицирует interference/penetration.

Возвращаются исходные цели, nearest_component_a/b, distance_mm,
closest_points_mm, closest_points_assembly_mm, полные leaf IDs, leaf/solid/
excluded nonsolid counts и evaluated/native/shared pair counts. Для каждой
выбранной детали closing gate повторяет body membership/summary и geometric
moments; для всего root — hierarchy/config/model identities, transforms и
observation. Scalar и witnesses finite, norm согласована. Scoped snapshots
не являются полной BREP mutation revision; не обещается физическая collision
классификация или обнаружение всех равномоментных изменений геометрии.

Бюджеты:1000 part leaves на цель,5000 normal bodies суммарно по уникальным
leaves,10000 solid leaf pairs. При превышении возвращается known refusal,
никакого неполного минимума. Проверки масштабирования1000+ остаются в плане.
Неразрешённые/lightweight/suppressed/SpeedPak, meshes и assembly-cut user
bodies пока не поддержаны. Point/axis distance агрегатов и native named frames
этот инструмент не реализует. Никаких implicit resolution, UI selection,
activation, rebuild, новых сущностей или операций библиотеки. Timeout ожидания
не отменяет COM; идентичный request_id возвращает прежнее задание/результат.

SOLIDWORKS API [ClosestDistance](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~ClosestDistance.html)
поддерживает multi-body part component и не предоставляет такой solver для
multi-part subassembly; поэтому здесь вычисляется минимум по normal leaves.
[ReferencedConfiguration](https://help.solidworks.com/2025/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IComponent2~ReferencedConfiguration.html)
меняет configuration context и может инвалидировать прежний descendant census.
В native fixtures после явных изменений перечень получают заново; инструмент
проверяет исходный контекст и не переключает конфигурации.
