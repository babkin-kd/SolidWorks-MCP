# Приёмка расстояния от экземпляра до бесконечной оси

**Принято 11.10.2026:** dev77, `resolved_part_component_axis_distance_v1`.
4335 pure passed/323 CAD deselected (54,63с); installed metadata62 инструмента/
18 guarded операций. Internal native18/public MCP6 на одном exact wheel,
оба accepted=true с первого прогона. Skipped CAD не засчитаны.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `4a0a02c20049ea2ae3c4e9389353ff74c6d9152c` |
| Source digest | `ad6c923da7825d87154a10d4aba563571c2837c57e9d4c28f6d23979cafac647` |
| Wheel SHA256 | `d8e2c19834d0d19386b17909421466ceb480b33ff406e2096e931d1573da40ed` |
| Verifier SHA256 | `9026204be1914038d4b9bac7de9a19e2019617eb4558113c9981e7d3cc1cee52` |
| Fixture helper SHA256 | `f68f54779ea0c83669174d272d3f630e4402a1a9e78b76495a454acd103d0306` |
| Internal report SHA256 | `8517c5f0b7df77cf2b941bed07aeaecf1efa63bcec0325b19f9e62b796201b7a` |
| Public report SHA256 | `1d3c792b2064ca8c9bc1a0c04bd904e9a52f665421c3cc8d51416be9f6168df9` |
| SolidWorks revision | `31.2.1` |

[Контракт](COMPONENT_AXIS_DISTANCE.md). Installed dev site-packages, без
PYTHONPATH исходников; отдельная рабочая v1 не менялась. Internal — installed
domain/native adapter и private journal. Public — настоящий console/stdio MCP,
metadata/output schemas, native цепочка, журнал и request replay.

| Фактическая CAD-операция | Независимый ожидаемый результат |
| --- | --- |
| Hidden rotated instance → root Y axis | 5 мм |
| Explicit rigid frame axis | 5 мм; body witness local X20/root Y30 |
| Cylinder → parallel root Y axis X158 | 2 мм до поверхности; не axis offset8 мм |
| Main multibody → Y axis X65 | 5 мм до hidden solid; surface исключена; два solid |
| Nested instance → Y axis X155 | 5 мм, total root transform |
| Oblique line Y=X−25, Z2.5 | 5/√2 мм, exact directional span |
| Origin перенесён по оси на Y1e6 мм | Те же 5 мм, finite-span результат не зависит от точки начала |
| Direction reversed/scaled | Те же 5 мм |
| Cylinder axis / tangent parallel line | Ноль в обоих случаях, без intersection classification |
| Replay | Та же operation/result, повторного solver нет |
| Zero vector / subassembly target | Known refusal до solver |
| Stale observation / inactive config / foreign root | Known refusal без implicit activation |
| Native referenced configuration replacement | Старый CID rejected, без reassignment |
| Native surface-only instance | Known component_has_no_solid_bodies |

Все18 detailed cases — internal. Public6 покрывает hidden rotated, explicit
frame, cylinder surface gap, replay и два отказа контракта; это не повтор всей
исторической CAD-матрицы. Pure отдельно проверяет mirrored transform math,
числовые крайние случаи, closing races, temporary-wire validations и protocol
oracle; native mirrored instance в этом блоке не проверялся.

Diagnostic `work/axis-distance-probe-1` до реализации подтвердил temporary
wire/edge binding и отсутствие изменения source state. Raw unbounded ICurve
native solver не принял; это отдельная диагностика, не приёмка инструмента.
В окончательной реализации span вычисляется exact body supports, а не
произвольным отрезком. Нового эскиза/элемента в CAD-дереве не создаётся.

После каждого terminal read независимо сравнивался source state всей own
сессии: document metadata, views/selections, body facts и полный instance/
configuration/transform state. Internal journal:13 succeeded/7 failed;
public:14 succeeded/2 failed. Все записи mutates=false/terminal; unknown/holds
нет. Перед cleanup подтверждены exact4-owned identities, blocking0, CIP=False
и non-STL preferences. Оба прогона закрыли только own docs, восстановили пустой
free baseline и настройки с readback. CAD/reports/journals остались в ignored
work/, не в публичном Git.

Scope остаётся ограниченным resolved part instances/normal solids. Aggregate
subassembly, native named frames, прочие native states и итоговый N0–N6 остаются
в [матрице](STAGE_1_REQUIREMENTS_MATRIX.md). S1-06/S1-16 и стадия1 открыты.
Все коммиты локальные; push/GitHub Actions не запускались.
