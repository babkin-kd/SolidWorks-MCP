# Приёмка точки и оси для агрегата компонентов

Принято 11.10.2026 в ограниченной области dev79: **4409 pure passed,
323 CAD deselected** (57,25 с), installed metadata65 инструментов/18 guarded
операций; internal native24/public MCP8 на одном точном wheel, accepted=true.
Общий N0–N6 и стадия1 остаются открытыми.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `b11c8b592830b3a360970c0b9809b3e684d0a83a` |
| Source digest | `8ad96a477b086da31bfd4924e2aff0b24f7bab03106549c43885393da99a7d3f` |
| Wheel SHA256 | `d2d66cdaebb5f9635aa375dc6e0084df6bbc572e1ca94bb87c21a397d9ee145f` |
| Verifier SHA256 | `4632b410ff615bec2b033afa332bf01b43a4b04da04913f80c64af26feeebe64` |
| Aggregate fixture SHA256 | `8d62acaa57c91e2ffc251c04d1f3837115fe6c4144ad817645bd6682959eb401` |
| Base fixture SHA256 | `f68f54779ea0c83669174d272d3f630e4402a1a9e78b76495a454acd103d0306` |
| Internal report SHA256 | `a7b37add4e07e49934f9952eedc2336b78037ffc71a36d500d340336d108225d` |
| Public report SHA256 | `f673f47706c783fb5c21ba31bbb4d306f29afa8a3fb707ec963567fd20c0adc6` |
| Metadata report SHA256 | `d14b73b1768def13e8a677541a94625aeaa8094c8b38364d19cdaf8520ed2f17` |
| SolidWorks revision | `31.2.1` |

[Контракт](COMPONENT_AGGREGATE_PROBES.md). Установленный пакет из dev
site-packages, без PYTHONPATH исходников. Отдельная рабочая v1 не менялась.
Internal проверяет домен/native adapter и журнал; public использует настоящий
console/stdio MCP. Искусственные pure-сценарии учитываются отдельно.

| Фактическая CAD-проверка | Результат |
| --- | --- |
| Точка снаружи hidden nested cylinder | 3 мм до поверхности; nearest original component/body/face; все9 solid faces |
| Точка внутри цилиндра / на границе | Положительные6 мм /0 мм; native location inside/boundary, inside=true/null |
| Бесконечная ось рядом с цилиндром / через тело | 2 мм до поверхности /0 мм; оба solid leaves измерены |
| Explicit shifted/rotated rigid frame | Оба инструмента, независимая проекция witnesses |
| Far origin/reversed direction | 2 мм, бесконечная линия без зависимости от знака направления |
| Part target и общие part helpers | Новые aggregate инструменты и прежние part point/axis возвращают5 мм для2 тел |
| Native смена referenced configuration | Старый parent ref отвергнут; свежий полный состав3 solid bodies даёт5 мм для точки/оси |
| Stale/foreign/inactive/zero direction | Проверенные known refusals; нет скрытой активации |
| Native подавление всех solid features | Оба инструмента отказали component_has_no_solid_bodies |
| Request replay | Та же операция и результат для точки/оси, без повторного solver |

Public8 покрывает outside/inside, explicit frame для обеих операций, replay
и inactive configuration. Остальные подробные сценарии — internal24.
Pure дополнительно проверяет budgets до solver, nonsolid leaf closure,
изменение nonwinning leaf/moments/supports и readonly runtime; эти случаи
не переобъявляются фактическими native-операциями.

После каждого read сравнивалось независимое состояние всех4 собственных
документов: metadata/views/selections/body facts, полная hierarchy/configs/
transforms. Internal journal: 17 succeeded/8 failed;
public: 16 succeeded/1 failed. Все записи readonly/terminal.
Cleanup проверяет exact4-owned identities, blocking0 и CommandInProgress=False.
Контрольные документы закрыты; пустой/free baseline и non-STL preferences
восстановлены. Новых unknown/holds нет. Это не отдельная приёмка STL.

Полное wall time internal/public: 300.58 / 116.98 с, включая setup,
проверки исходного состояния и cleanup. Per-case protocol_and_job_wait_seconds
включает ожидание задания; это не изолированное время COM solver. Cleanup/setup
для этого v2-стенда отдельно не измерены; общую экономию не заявляем.
Первый полный pure-прогон:4408 passed/1 failed (устаревшее ожидание63 tools),
после обновления ожидания итоговый4409 passed. Прежний отчёт не подменён.

Point минимум относится к индивидуальным solid boundaries, включая внутренние
границы перекрывающихся частей; Boolean union не строится. Axis0 не является
классификацией interference. Unsupported native states, native named frames,
1000+ scaling и общий gate остаются в [матрице](STAGE_1_REQUIREMENTS_MATRIX.md).
Следующий обязательный блок — native open/save/close (S1-15).
Legacy-пилот20/20 имеет собственные source receipts и не заменяет v2.
Пакет dev79 пока локальный; прежний remote CI-blocker dev78 не закрыт.
CAD, journals и полные отчёты остаются в ignored work/.
