# Локальная контрольная точка dev92: exact dimension ownership B1

Dev91 extrusion unknown сохранён и reconciled по независимо подтверждённой
пустой исходной сессии. Root не закрывал отсутствующие fixtures и не приписывает
это accepted cleanup неудачного driver. [Факты dev91](CHECKPOINT_DEV91.md#результат-после-возобновления).
Цель возобновлена; L2 не расширен, B1 и стадия1 остаются открытыми.

## Точный установленный кандидат

- Версия: `2.0.0.dev92`.
- Git: `dcc71c7c63ea455324db0219432d29d268b888e3`, clean build.
- Source digest: `69444b88b6b0b9faf6e38283b34bb41b45636f6a4bdaea0d06bc9861b7db1b2a`.
- Wheel SHA256: `63daff9776f915a4d480940283d67dacbc06e42683e6ec3eff0a61e23f613fa1`.
- Full source pure: **6686 passed /323 CAD deselected,153,31 с**.
- Offline wheel gate и installed metadata/stdio: **79 tools /25 mutations**,
  exact schema/provenance приняты, без source `PYTHONPATH`; CAD tools не вызывались.

Установлен только в dev .venv; рабочая v1 сохранена. Private evidence:
`work/pytest-dev92-full-1.log`, `work/wheel-dev92-report-1.json`,
`work/metadata-dev92-report-1.json`. Реальные модели и journals остаются вне Git.

## Исправление и проверки

Native interop dev91 подтвердил, что singleton extrusion display chain содержит
depth и absorbed width/height. Новый reader использует complete feature tree и
доказывает владельца каждого размера, затем выбирает только exact owned feature.
Borrowed dimensions допускаются лишь со старыми baseline annotation views;
неподтверждённый owner/view запрещает запись/retirement. Related73 pure/0,27 с.

Отдельный агент изменил только public supervisor и sibling loader: strict
rectangle committed/rolled_back gates без generic fallback, guards/ledger/full
geometry/restoration proof. Related267/14,63 с, neighbor56/6,94 с на artificial CAD
и real JobStore. Root проверил diff и интегрировал; единственный native владелец
сохранился. Полный6686 включает эту интеграцию; наборы не суммируются.

## Короткий native bridge interop

На установленном dev92 одна own fixture прошла отдельные sketch → extrusion →
owned extrusion inverse → owned sketch inverse;46 pending/returned rows, terminal/
exit0, own_count0, original baseline/application/non-STL restored. Borrowed sketch
и его views сохранились после extrusion inverse; исходный единственный view
восстановлен после sketch inverse.

Report SHA256: `9ad20f6b5c6d2d4622faa7063903a7a31a33bf1c9cad1939f0e78c61d896a6fb`.
Это interop механики native-мостов, **не полная B1 domain/MCP приёмка**: без
реального durable request/checkpoint, independent whole-session effect admission
и публичного фасада. `native_b1_accepted=false` сохранён.

## Оставшиеся gates и текущий прогон

Новый exact installed positive driver запущен:
`work/native-rectangle-dev92-positive-1/report.json`. Новый state/request, старый
unknown не повторяется. Один CAD-владелец; текущий wheel/helpers фиксированы
до terminal/quiescence. Running не засчитывается как accepted.

Этот промежуточный статус заменён фактическим результатом и независимой
очисткой ниже. Полная positive-проверка не принята.

После принятого positive нужны finite N4/N5 driver и public MCP на этом wheel;
затем B2 → B3 → B4 → B5. Imports/export/STL остаются отложенными D-задачами.
Локальные коммиты накоплены; нового push/CI нет.

## Подготовка отчётов N4/N5 и пауза 12.10.2026

По прямому запросу пользователя разработка ставится на паузу после локальной
фиксации текущего ограниченного блока. Новые native-прогоны, сборки wheel и
расширения B1 не запускаются. Уже работающий positive verifier оставлен
завершаться в фоне: прерывание процесса не доказывает отмену COM. До его
terminal/quiescence SolidWorks занят, установленный wheel и десять helpers
positive-прогона менять нельзя.

Завершена подготовка пассивного общего gate positive/N4/N5:
`scripts/verifier_rectangle_internal_acceptance.py`. Он требует отчёты одного
точного wheel, конечный manifest, настоящие domain jobs и журнал, полный
baseline, точную принадлежность foreign-ссылок и независимые before/after
снимки каждого случая. N4 обязан сохранить snapshot и счётчики без изменений;
N5 подтверждает ровно одну собственную запись и один управляемый Python-отказ,
с полным восстановлением. Это только preflight будущей public-проверки,
`native_b1_accepted=false`: искусственные тестовые сценарии не доказывают CAD.

В ещё не запущенный `verify_rectangle_stages_faults.py` добавлены сырые
доказательства этих проверок: reference scope, полный foreign feature listing,
шесть пар снимков, аргументы и счётчики dispatch. Frozen positive helpers и
установленный пакет не изменены. Связанные preflight-тесты: **20 passed /0,49 с**.
Финальный связанный регрессионный набор — **176 passed /29,56 с**, включая
51 новый тест общего gate и существующие positive/prewrite/native-verifier/
restoration suites. Все эти случаи pure с искусственным CAD; физическая
native-приёмка ими не заменяется. Наборы 20 и176 перекрываются и не суммируются.
`py_compile` и `git diff --check` прошли. Private log:
`work/rectangle-internal-acceptance-related-tests.log`. Агент закончил работу;
полный pure-набор и новый wheel не нужны для этого внешнего verifier-блока.

При возобновлении сначала проверить unified session **44035**, private
`work/native-rectangle-dev92-positive-1/report.json`, реальный процесс и журнал.
Последнее наблюдение перед фиксацией: `phase=sketch_job`, результата positive
ещё нет, ошибка не зафиксирована, snapshot соседа выполняется. Эти данные
промежуточные, а не итоговый статус. Драйвер сам выполняет проверенную очистку
после успеха; при failed/retained/unknown требуется независимое согласование
состояния и точная собственная очистка без повторения старого request.

Только после подтверждения quiescence, cleanup/baseline и фактического исхода
можно продолжить конечные N4/N5 на том же wheel, затем подготовить и выполнить
public B1. Public driver пока не реализован. B1–B5 и стадия1 открыты;
L2/L3 и S1-B5-ACT сохраняют прежние принятые границы. Push/CI не запускались.

## Проверка завершения и безопасная очистка 12.10.2026

По запросу пользователя проверен фактический исход оставленного verifier.
Он завершил сценарий **failed /positive_case_passed=false**, длительность
**3475,04 с**. Отдельный sketch job/replay прошёл, extrusion остался
**unknown/unresolved**: native postconditions не подтверждены, а полное
доказательство собственного эффекта не позволило безопасный inverse.
Это не успешная приёмка B1; исправление дефекта во время паузы не выполнялось.

Независимая проверка private journal подтвердила 22 строки/11 пар
pending→returned, 74 завершённых snapshot captures, отсутствие pending
native-call/creation/sketch-close/selection и освобождение обоих model guards
и application guard. Процесс находился в retained-цикле ожидания после
AssertionError, а не выполнял CAD. Его точные launcher/worker PID и родство
проверены; остановлен только завершённый verifier после доказанной quiescence.

Перед очисткой дважды сопоставлены точные HWND документов, метаданные и
update stamps, режимы без редактирования/блокировок, полный feature tree и
его persistent references в области исходного snapshot. Учтено, что snapshot
исключает PID служебных folder/display features: сами их строки дерева
сравнивались полностью. Все данные принадлежали двум нормально созданным
fixtures; пользовательские документы не обнаружены и не закрывались.

**Без сохранения закрыты ровно две собственные контрольные детали.**
Каждый CloseDoc вернулся и подтверждён исчезновением точного canonical token;
retired handles больше не читались. Независимый двойной readback подтвердил
пустой document/window census, ActiveDoc=None, CommandInProgress=False,
полный исходный baseline/application и non-STL preferences. Собственный
служебный флаг восстановлен. Private evidence:
`work/native-rectangle-dev92-positive-1/cleanup-quiescence.json`,
`independent-cleanup.json`, `independent-reconciliation.json`.

Hold согласован через `accept_current_state` по доказанной пустой сессии:
mutation phase **reconciled**, исторический job status **unknown сохранён**.
Старый request не повторялся, результат не объявлялся succeeded, исходный
failed report сохранён неизменным. Новые native-тесты/wheel/push/CI не запускались.

**Разработка остаётся на паузе. SolidWorks свободен от контрольных документов
и verifier этой проверки.** При возобновлении сначала разобрать фактический
postcondition-дефект extrusion dev92 и создать следующий проверяемый кандидат;
N4/N5 и public B1 не запускать на основании этого failed positive. B1 и стадия1
остаются открытыми.
