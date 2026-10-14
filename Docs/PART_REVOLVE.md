# Полное вращение основания — контракт и приёмка dev52

Установленный **dev52** принят для цепочки «новая деталь → полное вращение прямоугольного профиля, радиус 10 мм, высота 30 мм»: **2521 pure passed, 323 CAD deselected; fresh same-wheel internal 5 native passed и public MCP stdio 7 native passed, оба accepted=true**. Каталог — **30 инструментов, 8 mutations**. Подтверждены полностью определённый собственный профиль и ось, полный цилиндрический BREP (0 вершин, 2 замкнутых круговых ребра, 3 грани), независимые native объём около 9424,777961 мм³ и площадь 2513,274123 мм², stale-отказ до записи, scoped restoration после реального создания вращения и повтор request_id без второй операции. Исходная деталь, выделение/marks, вид и non-STL настройки сохранены; свои модели закрыты, сессия свободна. Приёмка ограничена этой цепочкой: исторические проверки других scope не засчитываются за новые прогоны dev52. Импорт/экспорт отложены; стадии плана остаются открытыми.

## Инструменты и границы

| Инструмент | Назначение |
| --- | --- |
| `part_prepare_base_revolve` | Полное read-only чтение пустой детали и явной плоскости; ревизия параметров/оси и ожидаемые объём/площадь. |
| `part_create_base_revolve` | Собственный полностью определённый профиль, собственная ось mark 4 и полный оборот; checkpoint, постусловия, scoped restoration. |

Scope `empty_part_full_turn_cylinder_revolve_v1`: явные document/configuration, текущий opaque `plane_object_id`, активная пустая writable деталь с одной конфигурацией, плоскость в начале координат. `radius_mm` и `height_mm` — конечные положительные миллиметры, от 0,001 до 10 000 000; `axis="profile_y"` фиксирует собственную линию x=0 профиля. Поиск первой оси/плоскости, активация чужого документа и сохранение файла не выполняются. Русские имена: «Эскиз вращения», «Вращение основания», «Тело вращения»; размеры «Радиус», «Высота вращения», «Угол вращения».

Сектор, конус, полое тело, произвольный профиль/ось и редактирование существующего вращения остаются в плане. Запись 360° через общий `dimension_set_value` запрещена прежним контрактом; изменение радиуса/высоты этого эскиза не входит в принятый контракт прямоугольной выдавленной базы. Библиотечные стандартные компоненты не переименовываются ради локализации.

## Полная геометрия и ревизия

Reader `right_circular_cylinder_brep_v1` читает два полных native CircleParams/CurveParamData с периодом 2π, оба плоских торца, CylinderParams, все loop/coedge-связи, их ориентацию/партнёров и полные root-массивы. Замкнутые круговые ребра здесь не имеют endpoint IVertex: нулевой census не означает отсутствующую геометрию. Каждое native double сохраняется как exact `float.hex`; отсутствуют округление, tessellation, bounds или частичный fallback. Check3 и closing census проверяются на каждом полном чтении; два полных чтения окружены проверками документа, конфигурации, native ownership, полной сети ограничений и event revision. Counts только выбирают reader, затем он доказывает весь topology/surface/curve contract.

Полностью плоский набор тел сохраняет прежний `planar_polyhedral_brep_v1`. Набор с цилиндром получает `planar_or_right_cylinder_body_set_v1`, с отдельным полным scope каждого тела. Seam/split-цилиндры, отверстия в пластине и произвольная смешанная криволинейная граница требуют дальнейшего расширения reader, текущий код их отклоняет.

Собственная ось берётся из точного возвращённого сегмента профиля и проходит свежий persistent-reference round trip, owner/native-state proof и точную проверку endpoints. Проверяется фактическое выделение собственного профиля mark 0 и собственной оси mark 4. Операция должна вернуть exact native Revolution; удержанные handle используются для постусловий и восстановления. Совпадение имени/координат не разрешает принять чужой объект.

## Журнал и восстановление

Параметры и полная ревизия повторно проверяются внутри durable mutation guard. Checkpoint предшествует изменениям CAD/UI. Повтор request_id читает тот же результат, тайм-аут ожидания не отменяет COM. Известная ошибка после создания собственного feature восстанавливает пустую деталь только при доказанной сохранности baseline, точных собственных объектах, параметрах/геометрии и отсутствии чужих зависимостей. Чужое изменение, неизвестное создание или selection удерживает application gate; автоматический повтор/удаление не допускается.

## Точная установленная сборка и evidence

- Version: `2.0.0.dev52`; clean package Git SHA: `db37a33e400a190a5ae116f2f09b4d56fd70e751`.
- Wheel SHA-256: `de434cd5b72206077c49e096744c2d822019242ea17bf213bd57c604c97b5080`.
- Package source digest: `9ff1b7a7a01aaf012659057f399d8ee3d0b508ecd816e9f861bc946da8453a0e`.
- Pure: 2521 passed, 323 CAD deselected; дополнительно 1 passed для контракта исправленного публичного верификатора. stdout/SQLite/artificial-CAD тесты не являются native-приёмкой.
- Metadata installed wheel: 30 tools, 8 mutations; console/stdio/provenance accepted, без CAD-вызовов.
- Internal: 5 passed; stale refusal, genuine creation/rebuild followed by injected known failure and scoped restoration, затем независимое успешное вращение. Native volume `9424.77796076938` мм³, area `2513.274122871834` мм².
- Public: 7 passed; создание документов, сохранность исходного, read-only preparation, вращение через публичный MCP, журнал и repeat request_id. Native volume `9424.77796076938` мм³, area `2513.274122871834` мм².
- Exact own fixtures закрыты после terminal proof; исходная пустая сессия/non-STL preferences подтверждены. STL не экспортировался.

Первый публичный запуск остановлен до отправки заданий: в новом проверочном скрипте отсутствовали ToolSpecs трёх документных операций, SDK ожидал cleanup proof пустого tracker. Удаления CAD не выполнялись; фактический журнал подтверждает 0 jobs/0 mutations, проверенные собственные процессы завершены. Добавлены явные specs и отдельный pure-тест покрытия; принятый публичный результат получен во втором свежем запуске на том же неизменённом wheel. Это ошибка harness, не неизвестный исход CAD-операции и не повтор native mutation.

До сборки выполнялся короткий source-candidate probe на двух временных kernel-цилиндрах (обычный и повёрнутый/смещённый), без создания CAD-документов. Это только API-проверка, отдельно от приведённой installed/native-приёмки постоянной feature-операции. Private CAD/job/log/report evidence хранится в ignored `work/` и не публикуется в Git.

Native API основание: [FeatureRevolve2 и selection marks](https://help.solidworks.com/2021/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeatureManager~FeatureRevolve2.html), [тип Revolution](https://help.solidworks.com/2022/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeature~GetTypeName2.html), [CylinderParams](https://help.solidworks.com/2022/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISurface~CylinderParams.html), [NULL endpoint замкнутого ребра](https://help.solidworks.com/2023/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEdge~IGetEndVertex.html).
