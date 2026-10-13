# B2: body identity после вставки плоскости — 14.10.2026

Третий N5 child-plane отказал после шести normally returned setup pairs:
составная проверка single body census/canonical/PID не прошла. До
preview/delete дело не дошло. Actual SQL сохраняет один unknown/unresolved,
reconciliation=None; setup нельзя считать committed. Root подтвердил84
returned captures, отсутствие active SQL и pending native, неизменные
creation jobs и31 frozen helpers. После завершения только exact idle test-owner
отдельная инспекция получила два одинаковых текущих состояния; две собственные
детали закрыты без сохранения. Полный baseline/CIPFalse/non-STL восстановлены,
исторический журнал неизменён.

Короткая диагностика выполнена на exact installed dev96, build Git f80ee6d,
wheel SHA9088e018; package source и установка не менялись.

| Проба | Actual результат | Очистка |
| --- | --- | --- |
| 1 | Ошибка Python interface lookup: Select4 вызван через IFace2 вместо IEntity; отказ до выбора грани/InsertRefPlane, все13 выполненных steps returned | Exact idle probe-owner освобождён; собственная деталь закрыта, baseline/CIPFalse восстановлены |
| 2,6,08 с | Для собственного основания40×20×10 мм после InsertRefPlane, rebuild и rename current body canonical отличается от исходного; PID тот же, native IsSame int1, current PID roundtrip и GetBody-владение шести граней исходной операции подтверждены. Габариты/объём8000 мм³ сохранены | Normal exit0, собственная очистка/full baseline |
| 3,6,19 с | Финальный `bind_current_body` фактически прошёл во всех четырёх фазах: до плоскости, после InsertRefPlane, после rebuild, после rename | Normal exit0, собственная очистка/full baseline |

Эти наблюдения воспроизводят несовпадение COM canonical при native equality
в ограниченной пробе. Они не принимают весь N5 и не позволяют вывести из
старого составного error-message конкретное нарушенное условие без наблюдения.

`verifier_b2_body_binding.py` принимает только явно выбранный native bridge:
original body/feature handles, один current body, исходный непустой bytes PID,
строго int1 от IsSame и current PID→точный current canonical. Полный GetFaces
исходной операции должен дать шесть различных original faces; QueryInterface
сохраняет own canonical каждой грани/тела, все GetBody указывают на единственное
текущее тело. Две границы и final census/PID закрывают изменения внутри
последних native callbacks. Shape/name не создают владение; fail не имеет
fallback/retry или полномочий на cleanup/acceptance.

N5 target сохраняет исходный body handle. Для topology/ancillary использует
только доказанно эквивалентный current body; closing capture требует тот же
current canonical в пределах наблюдения. Полный BREP, metadata/neighbor,
dimensions/references и event envelope остаются обязательными. Strict canonical
путь остальных callers сохранён; native owner явно выбирает bridge до fixture.
Следующий driver фиксирует32 helper SHA; принятые positive/fault helpers и wheel
не менялись.

Root integration160 pure/34,50 с прошла до последней дополнительной проверки
raw GetBody→QI canonical. Финальный связанный набор: **523 pure passed
/54,38 с**, normal exit0, без CAD. Full
нового source-кандидата и фактический N5/public остаются gates. Независимый
тестовый агент работал только с pure-файлом, не подключался к SolidWorks.

Source-кандидат зафиксирован как39eeb8d. Запущен один итоговый full pure;
executable source/tests зафиксированы до его terminal результата. Отдельный
fresh N5 child-plane-4 запущен на прежнем exact installed dev96 после
подтверждённой очистки и короткой пробы. Positive SQL/helper preflight прошёл,
фиксируются32 helpers. Root единственный COM-владелец; текущая phase
fixture_creation, terminal acceptance пока нет. Это новый собственный fixture,
не повтор historical unknown. Пакет и установка dev96 не менялись.

SHA256 частных доказательств:

- N5 child-plane-3 report: `95bf4bae37f12a75a42eef59d5f1fd28d2dac639c573513779824d0e00905ae0`.
- Maintenance cleanup: `3d7a6f42f38e13e177b3684c9a2b5f6b6976dac418af1b0cdc6eefca804c93ef`.
- Probe2: `5efde9c8923b1ad4532f4fa270af84b6d917ba206a2b9e5ae13dd65f945516d6`.
- Probe3: `0006be60eb46fbd40ca6741a35877ee7b07250585c57f6d54ce97c33e075c785`.

Полные CAD-файлы, модели, settings и журналы остаются в private `work/`.
Стадия1/B2 остаются открытыми; уравнения и public B2 ещё not_run.
