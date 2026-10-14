# Приёмка габаритов детали — dev72

11.10.2026. **Принято в области BREP-детали**: internal14/public6 accepted=true
на одном чистом установленном wheel. SolidWorks2023/revision31.2.1, source
PYTHONPATH отключён. Стадия1 остаётся открытой; результат не подтверждает
измерения сборок/instance paths, distance, native named frames или общий N0–N6.

| Идентичность | Значение |
| --- | --- |
| Версия | 2.0.0.dev72 |
| Git SHA wheel | e69d1d5ef8ab60c1462b5fca412323046f6fad29 |
| Source digest | 0fc07138b7cd7baf5ef74e82766849fd644fa4d55a81422eaf097b69a194cd4c |
| Wheel SHA256 | 006dfdde8c45143987cd0c6759e73c2ca934f53ffe0548fc2c5c71abd38dda16 |
| Полный pure | 4122 passed /323 CAD deselected,52,25с |
| Installed console metadata | 52 инструмента/18 guarded операций,accepted=true; без CAD |

measurement_get_bounds/measurement.bounds, read scope
part_native_support_bounds_v1. Все/выбранное solid/surface BREP-тело, включая
hidden; явно заданные origin_mm и правые ортонормальные axes_in_model либо
model frame. Используются native extrema в ±направлениях выбранных осей;
повторные6 extrema каждого тела и полный body roster подтверждаются.
[Контракт и численные границы](BOUNDS_MEASUREMENTS.md).

## Фактическая native-проверка

В каждом запуске три собственных несохранённых документа: два раздельных блока
20×10×5мм и поверхность15×10мм в первом; чужой блок во втором; круговой цилиндр
Ø12×30мм с осьюY в третьем. Модели создавались только как fixtures legacy-builder,
не являются приёмкой v2 создания цилиндра/сборки. Все новые documents/features/
planes/sketches/bodies названы по-русски с readback.

Internal14: объединённые solids+surface; выбранное второе тело в повёрнутом
и смещённом frame; поверхность с нулевым extent; цилиндр с поворотом осейX/Z
и смещением; foreign body reject; solid filter; tilted surface filter;
неверный body-type reject; stale observation reject; reflection reject;
hidden solid included; другая конфигурация с одним телом; отказ ссылки
предыдущей конфигурации; inactive configuration без скрытого переключения.

Public6: все тела; выбранное второе тело в явном rotated/shifted frame;
surface; curved-cylinder frame; foreign body reject; request_id replay одного
задания. Вызовы timeout0 ожидались до terminal через job_get, fresh journal
проверялся supervisor. Подробные14 случаев не дублировались в MCP-стенде.

Формулы проверки независимы от production projection: углы известных блоков/
поверхности и support круга цилиндра. Для повёрнутого кругового сечения
проверены12мм transverse extents; проекция приблизительных углов AABB дала бы
больший размер. Исходный цилиндр дополнительно проверен по native объёму.

Источник до/после каждого основного измерения сверялся независимо:
document/configuration/update/save state, selection objects/marks, body identities/
names/types/visibility/topology counts, geometric moments, units/view. CIP=False
и model blocking state0 сохранены. Изменения visibility/configuration/suppression
делались только стендом в собственных terminal fixtures; геометрию измеритель
не менял. Exact-owned cleanup подтверждён:3 fixtures закрыты без сохранения,
пуст/free baseline и non-STL-настройки восстановлены. Ни одного unknown/hold.

## Локальные свидетельства

CAD/SQLite/полные отчёты остаются в ignored work вне публичного Git.

| Отчёт | SHA256 |
| --- | --- |
| work/native-bounds-dev72-1/report.json | 5382c27d45687292eb69f411c8cc3a451d35ae176cc3d780bb41c9a7193f9809 |
| work/native-bounds-mcp-dev72-1/report.json | 8ca0f4e88b8dd227aa74c0fdf3c5321a8d7e7deb38a5802a249b230a34ee4666 |

Verifier SHA256:fd8c53326d0fc38d64724d15a87e51df3ecce0e1eabce9020eeb5ed19e7a9ee0.
Связанные domain/native-shaped/runtime/facade/metadata/verifier checks:75 passed
перед полным pure-набором. Искусственное adversarial изменение roster/extrema
не объявляется native-аварией. Deselected323 не засчитываются как CAD-успех.

Габариты имеют численную точность native CAD-ядра и задокументированные допуски
сопоставления; это bounds fingerprint, не полная BREP revision записи. Frame
выбирается пользователем и не оптимизируется до minimum-volume OBB. Native
named-coordinate features/assembly/component frame и общие mutations/restart
здесь не проверялись. Историческая масса dev71 остаётся приёмкой своего wheel,
её сценарии не переобъявляются результатами dev72.

Коммиты и wheel накоплены локально; GitHub push/CI не запускались, v1 сохранена.
