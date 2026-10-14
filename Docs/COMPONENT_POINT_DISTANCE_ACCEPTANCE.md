# Приёмка расстояния от экземпляра до точки

**Принято11.10.2026:** dev76, `resolved_part_component_point_distance_v1`.
4287 pure passed/323 CAD deselected (53,93с), metadata61 инструмент/18 guarded
операций; internal native19/public MCP6 на одном exact wheel, оба accepted=true.
51 новых domain/parser/native-adapter/verifier tests до сборки; общий связанный набор97
прошёл до дополнительного adapter набора, затем связанные51 и итоговый full.
Диагностический probe5 отдельно подтвердил native binding/local coordinates,
trimmed closest point и native ENTER/EXIT без изменения source state. Он не
засчитан как приёмка реализованного инструмента.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `47f8b591c9fdfa4a11801c42c0c21c64cdaff33f` |
| Source digest | `b4a697c47635c55762d20c2837a833b8f2b1489b891df90220694e77e8bd5d2d` |
| Wheel SHA256 | `26bd1a9e31b61b7265bd36a7fc0719f8bbda032310690145fb03bf7f70f2cbf5` |
| Verifier SHA256 | `7f4e2037bd2e2b0752976c5f9cd3c95eb1eff049f227ee39f4cb2808c9235462` |
| Fixture helper SHA256 | `f68f54779ea0c83669174d272d3f630e4402a1a9e78b76495a454acd103d0306` |
| Internal report SHA256 | `f69d0917fd88cfa1224bca9fb36c45d09339fb0daabd640c25dbc66f835abd56` |
| Public report SHA256 | `d43cb48c7b8ff3204b1844dd7ba494359b29bc8b184b6dc7633b1a3b7aadcf4a` |
| SolidWorks revision | `31.2.1` |

[Контракт](COMPONENT_POINT_DISTANCE.md). Проверено из dev site-packages, без
PYTHONPATH исходников; рабочая v1 не менялась. Internal — installed domain,
native adapter/private journal. Public — настоящий console/stdio MCP,
metadata/output schemas, native пользовательская цепочка, журнал и replay.

| Native сценарий | Независимый результат |
| --- | --- |
| Hidden rotated point outside | 5 мм, nearest root50/20/22.5 |
| Hidden rotated point inside | Boundary distance2.5 мм, inside=True |
| Exact boundary | Ноль, point_location=boundary, inside=None |
| Replay | Та же operation/result, повторного solver dispatch нет |
| Nearest face/body original ID | Успешный component_topology_get для той же native face |
| Explicit rigid frame + trimmed corner | sqrt425 мм; frame nearest20/10/5, root40/30/25 |
| Hidden body в multibody + excluded surface | 25 мм; ближайшая surface2.5 мм исключена, counts2 solids/12 faces |
| Solid cylinder | Radial outside2 мм и axis inside6 мм; проверены root radial coordinates |
| Nested part | 5 мм, nearest root150/5/2.5 |
| Stale/inactive/foreign/subassembly context | Явные отказы без скрытого изменения состояния |
| Native changed referenced configuration | Отказ исходного ID без перепривязки |
| Owned original cylinder suppressed, new hollow solid | Старые nearest body/face references отвергнуты |
| Hollow cavity / material wall | 2 мм в обоих случаях; void outside и material inside |
| Surface-only part instance | component_has_no_solid_bodies |

Первая internal-попытка дала18 положительных cases, но accepted=false:
последняя fixture setup проверка требовала ShowConfiguration2=True для уже
активной Основной. Terminal readback подтвердил Основную; собственные4 модели
закрыты после подтверждения read-only terminal jobs. Неудачный отчёт сохранён
как непринятый. Верификатор теперь переключает только при необходимости и
обязательно подтверждает конечную configuration;4 новых pure tests, related14
passed. Installed package/wheel не менялись. Повторный fresh internal19 принят,
public6 принят на том же wheel и исправленном verifier SHA. Общий full4287
относится к package candidate перед этой control-plane правкой; новый полный
набор не заявлен и ради исправления верификатора не повторялся.

Native новая hollow fixture проверена независимо по volume pi32*30 мм3;
profile/feature/body названы по-русски. Это fixture setup, не заявление новой
публичной engineering operation. Distance — минимум до индивидуальных solid
boundaries; внутри остаётся положительным, не collision clearance и не минимум
до внешней оболочки union при перекрытии нескольких тел. Native mirrored
transform math проверена pure; реального mirrored экземпляра эта приёмка не
добавляет. Не заявлена универсальная приёмка произвольного BREP/состояний.

После каждой terminal read независимо сравнивался source state всей
контрольной сессии: document metadata, views/selections, body facts и полный
assembly instance/configuration/transform state. Журналы: internal{'succeeded': 15, 'failed': 7},
public{'succeeded': 16}, все mutates=false/terminal; новых unknown/holds нет.
Перед cleanup подтверждены exact4-owned identities, blocking0, CIP=False и
non-STL preferences. В обоих прогонах закрыты только own docs; пуст/free
baseline и настройки восстановлены с readback. CAD/полные reports/journals
остались в ignored work/, не в публичном Git.

Axis/aggregate-subassembly distance, named frames, прочие states и весь final
N0–N6 остаются в [матрице](STAGE_1_REQUIREMENTS_MATRIX.md). Full S1-16/S1-06/
S1-05 этим блоком не закрыты. Коммиты локальные, push/Actions не запускались.
