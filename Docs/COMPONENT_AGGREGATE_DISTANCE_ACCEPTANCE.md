# Приёмка расстояний агрегатов компонентов

**Принято 11.10.2026:** dev78, `resolved_component_aggregate_distance_v1`.
4365 pure passed/323 CAD deselected (54,78с), installed metadata63/18.
Internal native19/public MCP6 на одном exact wheel, оба accepted=true.
Приёмка scoped, стадия1 и общий N0–N6 остаются открытыми.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `e0f4e2f5c78461466817fe83d50a648d0771352b` |
| Source digest | `63ca5dafabf245da0365cd948791b0a4897dd4f15453973c4ef4379eefb66fb2` |
| Wheel SHA256 | `5ffc73d55b3e8a5061957f0f117a008ec8a6cd8d18ef79d450ef93785241aee2` |
| Verifier SHA256 | `9b38983fab51028430f1bc66f0b4c1c143cc83698952609518dec6677e7fdce4` |
| Aggregate fixture SHA256 | `8d62acaa57c91e2ffc251c04d1f3837115fe6c4144ad817645bd6682959eb401` |
| Base fixture SHA256 | `f68f54779ea0c83669174d272d3f630e4402a1a9e78b76495a454acd103d0306` |
| Internal report SHA256 | `f668114e37cf3ef1eaa77df45ef35810cf1ba8fb4318f6a777621d3178e8b179` |
| Public report SHA256 | `899a36210a1e3e378b70f2e3cb9527bff054c111b8c299024ecd6d5401bb763c` |
| SolidWorks revision | `31.2.1` |

[Контракт](COMPONENT_AGGREGATE_DISTANCE.md). Installed dev site-packages без
PYTHONPATH исходников; отдельная рабочая v1 не менялась. Internal проверяет
домен/native adapter/private journal, public — настоящий console/stdio MCP.

| Фактическая CAD-проверка | Результат |
| --- | --- |
| Part → полный агрегат подсборки | 70 мм, оба solid leaves учтены |
| Две повторные подсборки | 84 мм, все4 пары, hidden cylinder — минимум |
| Explicit rotated/shifted rigid frame | 84 мм, независимая проекция обоих witnesses |
| Агрегат → собственный descendant | 0;1 native pair/1 shared pair, exact solid witness |
| Reverse targets / обычная part pair | 84 /15 мм |
| Nested aggregate → rotated part | √6625 мм |
| Replay / inactive / stale / foreign / same target | Replay без нового solver; known refusals |
| Native referenced configuration change | Old parent/sibling/child refs rejected; обе цели relisted |
| Fresh complete multibody roster | 84 мм, solid body counts3/2 |
| Native ancestor rename / move | IDs сохранены при rename; после move текущий минимум0 |
| Агрегат без solid leaves | Known component_has_no_solid_bodies |

Public6 покрывает70/84 мм, explicit frame, shared descendant, replay и
inactive configuration; подробные отказы/rename/config/move — только internal.
Pure отдельно проверяет budgets, nonsolid leaf closure, full pair census,
closing races и другие состояния; они не объявлены native-доказательствами.

Три неуспешных внутренних прогона сохранены accepted=false: setup float
origin, устаревшая sibling reference после native смены configuration,
fixture rename без обязательного select/preference. Это исправления внешнего
стенда; исполняемый пакет и source digest после сборки не менялись. Добавлен
отдельный pure regression для sibling replacement; после ремонта31 related
passed (0,67с), но исходный полный4365 не переобъявлен новым полным4366.
Первый public запуск не подключился к COM в sandbox и не создал документов;
последующий запуск в desktop context принят отдельно.

После каждого terminal read сравнивался независимый source state всех4 own
документов, metadata/views/selections/body facts/полная instance hierarchy,
configurations и transforms. Internal journal14 succeeded/8 failed;
public15 succeeded/1 failed. Все записи readonly/terminal; новых unknown/holds
нет. Перед cleanup доказаны exact4-owned identities, blocking0/CIP=False;
закрыты только контрольные документы, baseline пуст/free, non-STL prefs
восстановлены. STL вне scope, полные снимки сохранены; это не приёмка STL.
CAD, journals и полные отчёты остаются вне публичного Git.

Point/axis distance агрегатов, native named frames, остальные native states,
1000+ scaling и общий N0–N6 остаются в [матрице](STAGE_1_REQUIREMENTS_MATRIX.md).
Legacy CAD-пилот не заменяет этот scope и не закрывает stage1 gates.
