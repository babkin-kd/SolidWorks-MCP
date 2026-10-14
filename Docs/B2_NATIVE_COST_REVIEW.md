# Стоимость native B2 dev97: пассивный снимок 14.10.2026

Прочитаны только два указанных `report.json`; обход `work/`, CAD/COM,
проверочные процессы, серверы и новые native-вызовы не выполнялись.
Сначала JSON-преобразование PowerShell без `-AsHashtable` отказало из-за
пустого имени свойства; числа получены повторным разрешённым чтением байтов
с `-AsHashtable`. Отказ парсера не являлся результатом CAD-проверки.

## Точные исходные артефакты

| Отчёт | SHA256 прочитанных байтов | Размер | LastWriteTime UTC |
| --- | --- | --- | --- |
| `work/native-owned-leaf-dev97-faults-1/report.json` | `5efb5fbce245b75f1c768c1ce0128e4bf7e2797faeea11f734bddacca610cb5e` | 2633267 bytes | `2026-10-14T05:32:48.7298546Z` |
| `work/native-owned-leaf-dev97-positive-1/report.json` | `3c69db9bdcb5a0e14ac760a3ac8543ae655701d79dcefdadc28ed5fb22f38671` | 2638358 bytes | `2026-10-14T04:06:42.0920986Z` |

Оба файла имеют scope `installed_rectangle_stages_positive_only`: это отчёты
исходного B1-владельца, на котором работают B2 hooks, а не отдельные
`leaf-positive-report.json` / `leaf-faults-report.json`. Последние здесь не
читались. Числа относятся к зафиксированным SHA; faults-файл может измениться.

Positive: `phase=terminal`, `native_calls_live=false`,
`elapsed_seconds=6023.186719799996`.
Faults: `phase=owned_cleanup`, `native_calls_live=false`,
`elapsed_seconds=5055.750991600013`. Его последний capture ещё `running`,
`started_s=5055.750989399996`, без `elapsed_s`. Промежуточный False в родительском
отчёте не доказывает окончания hook/process, native quiescence или cleanup.

## Captures по status/title

Суммы включают только `returned` с собственным `elapsed_s`. Median — среднее
двух средних значений при чётном количестве. В таблице секунды округлены
до 9 десятичных знаков, проценты до 6; количество строк точное.

| Прогон | Status | Title | Count | Сумма, с | Median, с | Max, с | Доля report elapsed |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| faults | returned | Контрольная деталь отдельных стадий | 49 | 1929.086583300 | 49.375858500 | 85.567082700 | 38.156282% |
| faults | returned | Рабочий сосед отдельных стадий | 44 | 2860.262953800 | 77.376395100 | 87.282177600 | 56.574443% |
| faults | running | Рабочий сосед отдельных стадий | 1 | не измерена | не измерена | не измерена | не измерена |
| positive | returned | Контрольная деталь отдельных стадий | 58 | 2283.580708300 | 52.253141850 | 88.850789600 | 37.913165% |
| positive | returned | Рабочий сосед отдельных стадий | 54 | 3424.590467700 | 79.193957650 | 86.945267600 | 56.856787% |

Faults: всего 94 capture rows, **93 returned / 1 running / 0 failed**.
Сумма returned `4789.349537100206` с; общий median
`70.55232980000437` с, max `87.28217759999097` с.
Доля суммы в записанном elapsed `0.9473072437818981` (**94.730724%**).
Остаток elapsed `266.4014544998063` с.

Positive: всего 112 capture rows, **112 returned / 0 running / 0 failed**.
Сумма returned `5708.171175999887` с; общий median
`74.09413829998812` с, max `88.85078959999373` с.
Доля суммы в terminal elapsed `0.9476995221209795` (**94.769952%**).
Остаток elapsed `315.0155438001093` с.

Сосед даёт большую часть измеренных capture секунд в обоих снимках.
Последовательные returned интервалы `started_s .. started_s+elapsed_s`
не перекрываются; последнее running исключено из сумм/median/max. Его
продолжительность нельзя получить из старого значения report elapsed.
Faults-процент характеризует сохранённый префикс, а не окончательный прогон.

Таймер `Observed.rectangle_construction_snapshot` охватывает полное чтение
и начальную запись отчёта перед `super()`, но не финальную `persist()` после
установки `elapsed_s`. Это стоимость обёртки наблюдения, а не чистый COM.
Отдельные `first_save_part_snapshot`, metadata/PID/guard getters, создание,
solver/rebuild, SQLite, финальная запись/cleanup не разложены по времени.
Поэтому остаток не следует называть стоимостью мутаций или solver; per-getter
COM и solver отдельно не измерены. Titles не дают точной атрибуции к phase/job.

## Обязательные чтения и повторы в конечном flow

В `verify_rectangle_stages_positive.main` обязательны независимые full
EMPTY → SKETCH → BASE, 8000 мм³, неизменный full сосед и terminal own
cleanup/baseline. Оба B2 wrappers повторяют эту B1 construction/admission
chain на новых собственных документах: видимое повторение относится к общему
setup/lineage разных positive/fault сценариев, а не к повторной leaf mutation.
Назвать этот setup лишним по двум JSON нельзя.

В `run_fault_cases` обязательны initial full preparation/current сравнение,
full unchanged state после stale/foreign и no-effect, released guard/ledger.
Для observation unknown `prove_quiescent_effect` требует два равных full
current/session снимка и sketch canonical/PID/old feature PID доказательства
до own cleanup; historical SQL unknown/hold сохраняются. Replay запрещает
второй dispatch. Эти повторные наблюдения выполняют разные проверки;
их стоимость не доказывает возможность удаления before/after/guard/PID gates.

## Три улучшения следующего стенда

1. В следующем helper добавить к capture уже имеющиеся case/owner/hook phase
   и purpose; это позволит отличить preparation от quiescence и acceptance
   без дополнительных CAD getters. Running остаётся незавершённым.
2. Измерить wall time групп существующих full-snapshot getters и отдельно
   persist/rebuild, начиная с соседа. Порядок, полнота данных, guard/PID и
   before/after сохраняются; оптимизировать только установленный узкий источник
   затрат, а не делать вывод о solver по общей длительности.
3. Не добавлять отдельный B1-native повтор после каждого B2 wrapper при том же
   wheel/helpers: owner уже выполняет его setup/admission chain. Не дублировать
   подробную внутреннюю faults-матрицу в MCP без конкретного контрактного
   основания; actual public user chain и полный independent observer сохранить.

Текущий процесс не отменяется и не перезапускается. Этот аудит не даёт
dispatch/cleanup authority, не закрывает faults/N5/public/B2 и не превращает
`not_run` в passed. Код, frozen helpers, `.venv`, Git и PLAN не менялись.

Прочитанные flow helpers: `verify_owned_leaf_deletion_faults.py` SHA256
`c44c0f7bdb4f877c9d77f5b1c954e1d6963783de04d48ed84b1eabd76016649e`;
`verify_rectangle_stages_positive.py` SHA256
`fbaab116ae2e07c27783e160cbda3f0ddf14183b2c4782942aa3d70114e3cf76`.
