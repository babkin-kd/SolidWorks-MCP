# Приёмка расстояния между экземплярами деталей

**Принято 11.10.2026:** dev75, scope `resolved_part_component_distance_v1`.
4236 pure passed/323 CAD deselected (53,88с), installed metadata60 инструментов/
18 guarded операций; internal native13/public MCP6, оба `accepted=true` на
одном exact wheel. Один новый passive tool. Diagnostic probe3 отдельно
подтвердил binding/transforms/unchanged state и не засчитан как приёмка tool.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `ce6ec44bfb5b15d472eb24bbdbb9c5912861fc5a` |
| Source digest | `6aef2f765ac3eb78b0a38b156b66311b38e4e95a50c1c6cafed1f166e6cce3ab` |
| Wheel SHA256 | `50a13c95b932e7011babde2a940c98eb2e1d8afcbd3c5ec301e7c036f0554bba` |
| Verifier SHA256 | `62f33646ec32868a579ae802d615f5761641bd63f3e3c3ba2d5c834b2ff7bc68` |
| Fixture helper SHA256 | `f68f54779ea0c83669174d272d3f630e4402a1a9e78b76495a454acd103d0306` |
| Internal report SHA256 | `bde31f93535e8aaabc6f00e60431b48db3b0da0223de38f56e0b798c7c93d3a8` |
| Public report SHA256 | `5f963fe0e3bf9a319ce75a958df06da770f494f6d3e3df8d1db6891a3401c942` |
| SolidWorks revision | `31.2.1` |

[Контракт](COMPONENT_DISTANCE.md). Проверено через site-packages dev-окружения,
без PYTHONPATH исходников; отдельная v1 не менялась. Internal использует
установленный domain/native adapter и private journal. Public — установленный
console/stdio MCP, output schemas, server metadata, публичный журнал и replay.

| Native доказательство | Результат |
| --- | --- |
| Hidden rotated instance + main multibody | 15 мм; counts2/1; обе точки внутри независимо известных root boxes |
| Вложенная деталь с total transform | 70 мм; native surface не входит, хотя находится ближе |
| Цилиндр пересекает прямоугольное тело | Native distance0; классификация объёмов не объявлена |
| Обратный порядок целей | Те же15 мм, точки в порядке целей |
| request_id replay | Та же operation/result; дополнительного solver dispatch нет |
| Подсборка как цель | Отказ unsupported_component_type |
| Internal stale/inactive/foreign context | Явный отказ без изменения модели/выделения |
| Native перемещение цилиндра | 14 мм; ближайшие root X150/164 |
| Native касание цилиндра | Ноль в установленном допуске |
| Два цилиндра | 24 мм; не36 мм между осями, witness X176/200 |
| Native смена referenced configuration | Старый instance ID отвергнут без перепривязки |

Internal13 и public6 приняты с первой попытки. Подробные transform/fault cases
не дублировались в публичной цепочке. Pure26 новых domain/verifier tests;
связанный набор51 перед итоговым полным прогоном. Первый full имел один отказ
версии registry template (4235 passed); версия исправлена, итоговый full4236
passed. Отказ первого прогона не считается успешным.

Перед каждой read и после terminal результата независимо сравнивался source
state всей контрольной сессии: native document metadata, views/selections,
body summaries, assembly instances/configurations/transforms. Все private
jobs terminal и mutates=false (internal:10 succeeded/5 failed; public:15 succeeded/1 failed); новых unknown/holds нет. После каждого прогона
проверены exact4-owned identities, blocking0, CommandInProgress=False,
настройки non-STL; закрыты только собственные модели. Пуст/free baseline и
настройки восстановлены с readback. CAD, журналы и полные reports остаются
в ignored work/, не в публичном Git.

Native named frames, расстояние до точек/осей, aggregate subassembly scope,
прочие assembly states и общий final wheel N0–N6 остаются в
[матрице стадии1](STAGE_1_REQUIREMENTS_MATRIX.md). Эта приёмка не является
collision/interference классификацией и не завершает S1-16 или стадию1.
Локальные коммиты; push/GitHub Actions не запускались.
