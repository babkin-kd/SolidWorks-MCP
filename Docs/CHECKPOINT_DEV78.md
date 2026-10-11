# Пакетная контрольная точка dev78 — 11.10.2026

Пакет после пяти связанных блоков: dev74 instance topology, dev75 pair
distance, dev76 point/location, dev77 infinite axis, dev78 aggregate pair.
Также включает прежний локальный backlog стадии1 и ограниченных инженерных
сценариев. Это одна отправка. Стадия1 открыта:22 строки матрицы,2 scoped done/
20 открыты. PR остаётся draft, main не обновляется.

| Привязка / проверка | Значение |
| --- | --- |
| Версия установленного wheel | `2.0.0.dev78` |
| Git исходников wheel | `e0f4e2f5c78461466817fe83d50a648d0771352b` |
| Source digest | `63ca5dafabf245da0365cd948791b0a4897dd4f15453973c4ef4379eefb66fb2` |
| Wheel SHA256 | `5ffc73d55b3e8a5061957f0f117a008ec8a6cd8d18ef79d450ef93785241aee2` |
| Git pure checkpoint/legacy harness | `95f0e58af9a6bf08a63eb46c58af5c47f0a6119c` |
| Полный pure checkpoint | 4373 passed/323 CAD deselected,56,80с |
| Pure перед wheel | 4365 passed/323 CAD deselected,54,78с |
| Installed metadata | 63 tools/18 guarded, accepted=true |
| Internal native / public stdio MCP | 19 /6 passed, оба accepted=true |
| Native v2 cleanup | Exact4-owned, empty/free baseline, non-STL prefs confirmed |
| Legacy cleanup-probe | 1 passed,3,31с wall/0,14с cleanup |
| Legacy pilot | 20 passed/0 failed/0 skipped/0 not_run/unknown=false |
| Legacy pilot время | 54,47с wall/2,996с cleanup, cleanup входит в общее |

После wheel менялись только внешние tests/verifiers/документы; package digest
повторно проверен и совпадает. После pure checkpoint — только документация.
Installed dev проверен без source PYTHONPATH; legacy выполнялся с PYTHONPATH=src.
Рабочая v1 не менялась. Pure mocks и metadata не считаются CAD-доказательством.
Точная [приёмка v2](COMPONENT_AGGREGATE_DISTANCE_ACCEPTANCE.md) и отдельный
[legacy реестр/пилот](LEGACY_CAD_BASELINE.md) содержат hashes/outcomes/ограничения.

Полный pure покрывает затронутые runtime/catalog/schema/STA/journal механизмы;
настоящий MCP dev78 — свежий каталог/readonly jobs/replay и aggregate scope.
Исторические native receipts dev74–77 остаются на собственных wheel;
они не переобъявлены регрессией dev78. Общий N0–N6 dev78 **not_run**.
Aggregate point/axis, named frames, остальные native states и scaling1000+
открыты. Даже успешный CI не завершает стадию.

Три internal attempts dev78 failed при ремонте внешнего стенда, первый public
preflight failed до CAD; сохранены accepted=false. Новые19/6 этого не меняют.
Новых unknown нет; исторические unknown-журналы сохранены. Whole native wall/
setup/diagnostic durations v2-блока не измерены; экономия времени не заявляется.
Legacy pilot не заменяет mandatory v2 и не вводит ежедневный323-run:
303 cases not_run в пилоте, многодокументная legacy cleanup открыта.
Import/export/STL отложены, неподтверждённые PDM/Simulation не добавлены.

CAD files/journals/полные reports/реальные пути остаются в ignored work/.
На GitHub идут код и обезличенная сводка через Git/API. Обязательный
`unit-and-build` проверяет актуальный PR HEAD. Его новый Git SHA/wheel не
получает native-приёмку локального wheel автоматически. Merge/release/
публикация этой контрольной точкой не выполняются.
