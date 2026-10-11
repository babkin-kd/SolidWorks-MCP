# Расстояние между экземплярами деталей

Кандидат dev75 реализует `measurement_get_component_distance` →
`measurement.component_distance`. Это passive read, каталог60 инструментов/
18 guarded операций. Native-приёмка должна относиться к точному wheel; pure
проверки сами по себе не подтверждают работу CAD.

Вход: request_id, явный document_id корневой сборки, активная configuration,
expected_observation_revision, разные component_a_id/component_b_id из
component_list. Повторное использование одного файла допускается: целями
остаются два отдельных экземпляра. Вложенная деталь допустима, сама подсборка
как цель отклоняется. Нет поиска по имени/индексу, активации, загрузки,
переключения конфигурации, rebuild или изменения выделения.

Scope `resolved_part_component_distance_v1`: fully resolved native part
instances, normal solid тела, включая скрытые. Surface тела не измеряются;
оба экземпляра должны иметь solid. Mesh, SpeedPak, unresolved и user тела
после assembly cut вне этой области, унаследованы от component body gate.
Полный assembly census также обязан пройти resolved instance gate.

Native [IModelDoc2.ClosestDistance](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~ClosestDistance.html)
получает сами компоненты, чтобы учитывать их полную трансформацию в корневую
сборку, включая вложенную подсборку и поворот. Возвращаются distance_mm,
closest_points_mm в порядке целей, coordinate_frame=assembly_model,
solid_body_counts, метаданные обеих целей и observation. Native SI метры
переводятся в мм без округления. Отрицательное/no-solution значение,
нефинитные/неполные точки, переполнение или несогласованная норма вектора
между точками отклоняются. Допуск нормы: abs1e-8 м, rel1e-8.

Ноль — результат native minimum distance. Инструмент не классифицирует
касание, объёмное пересечение и полное вложение; поле
intersection_classification=not_provided. Это не collision clearance или
проверка пересечений. Габариты не используются как замена solver distance;
измерение отдельных цилиндрических граней/осей не объявлено.

Перед и после solver проверяются root observation/config identity, полная
иерархия экземпляров, native identities, referenced configurations и
трансформации. Для двух целей проверяются persistent roundtrip и полное
membership normal solid/surface тел, local body summaries и geometric
moments каждого solid через GetMassProperties(1). Существующий fingerprint
моментов —12 значащих цифр. Это ограниченные read snapshots, не полная BREP
revision и не разрешение мутаций. При смене state во время измерения успех
не возвращается. Журнал хранит mutates=false; исход timeout не отменяет COM.

Приёмочный сценарий: hidden rotated/multibody15 мм, nested70 мм при более
близком excluded surface, curved overlap0, обратные цели, replay, отказ
подсборки; internal дополнительно stale/inactive/foreign context, native
move14 мм, tangent0, два цилиндра gap24 мм вместо axis36 мм и отказ старых
ссылок после referenced configuration change. Source state, выделение,
настройки, terminal jobs, exact-owned cleanup/baseline проверяются независимо.
Public chain проверяет контракт/журнал через установленный stdio сервер.

Расстояния до точек/осей, агрегат подсборки, named frames и общая приёмка
S1-16 ещё остаются; этот блок не завершает стадию1.
