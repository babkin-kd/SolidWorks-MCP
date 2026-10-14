# Габариты детали в явных осях — стадия 1

Кандидат dev72: measurement_get_bounds /measurement.bounds, read-only scope
part_native_support_bounds_v1. Каталог52 инструмент/18 guarded операций.
Dev72 принят:4122 pure/323 CAD deselected,metadata52/18, internal14/public6
accepted=true на одном wheel; exact-owned cleanup/baseline подтверждены.
[Приёмка](BOUNDS_MEASUREMENTS_ACCEPTANCE.md). Это реализация части S1-16/06;
assembly bounds/component paths, расстояния, native named-coordinate-system
features и совокупный итоговый gate остаются открытыми.

Явный document_id, активная configuration, expected_observation_revision,
request_id. Все solid/surface BREP-тела, включая hidden; фильтр all/solid/surface
или один persistent body_id, который должен соответствовать фильтру. До500 тел,
PID roundtrip и сильная native identity, без индексного fallback. Mesh запрещены.
Никакой скрытой активации, перестроения, установки CIP/lock или работы с selection.
Обычный read job, request replay/timeout/job_get следуют общей семантике.

GetBodyBox в body_list остаётся **approximate=True**. Для инженерного измерения
используется GetExtremePoint для ±направлений трёх выбранных осей каждого тела:
[GetExtremePoint](https://help.solidworks.com/2013/English/Api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IBody2~GetExtremePoint.html).
Это native support bounds с численной точностью CAD-ядра, не обещание абсолютной
математической точности. [GetBodyBox](https://help.solidworks.com/2022/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IBody2~GetBodyBox.html)
документирован как приблизительный; его углы не используются в этом инструменте.

coordinate_frame=None: оси модели. Явный frame содержит origin_mm и три
axes_in_model (осьX/Y/Z как vectors в модели), определяющие
p_model_mm=origin_mm+Σ(axis_i*p_frame_mm[i]). Finite правые ортонормальные оси
(tolerance1e-10), без масштаба/сдвига осей/отражения. Это явно переданный rigid
frame; он не связан с persistent feature одноимённой native системы координат.
Bounds являются AABB в выбранных осях, не автоматически minimum-volume OBB.

Результат: bounding_box_mm.min_mm/max_mm/size_mm, явный полный frame,
body_ids/count/type, method=native_extreme_points и read_postconditions.
SI точки переводятся в мм, origin применяется после проекции. Теряемая из-за
чрезмерной translation точность размера отвергается (1e-8мм absolute/1e-10 relative).
Плоская surface допускает нулевой extent. Обратные границы вне1e-8мм запрещены;
меньшее численное расхождение сводится к одной координате.

После первого прохода подтверждаются документ/конфигурация/rebuild, полностью
сверяется closing body roster/PID/native identities/type/opaque refs и повторяются
все6 extrema каждого тела. Расхождение1e-8мм absolute/1e-12 relative запрещает
success, затем ещё раз подтверждается контекст. Это bounds fingerprint, не полная
ревизия BREP для записи. Изменение формы, сохраняющее bounds, само по себе не
меняет результат этого чтения; полные mutation revisions остаются отдельным gate.

Проверки блока: аналитические/adversarial domain tests, native-shaped contracts,
runtime/facade и stdio metadata; затем installed-wheel detailed native и public
protocol без повторения всех физических отказов. Skipped не засчитываются.
