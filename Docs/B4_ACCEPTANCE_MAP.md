# Конечная приёмка B4: диагностика и восстановление

Карта оставшейся работы по шести условиям
[B4](STAGE_1_BLOCK_ACCEPTANCE.md#s1-b4--диагностика-и-восстановление).
Составлена без CAD-вызовов и изменения исполняемых файлов во время native B1
dev93. Ни одно условие этим документом не объявляется принятым.

| Условие | Пользовательский результат | Имеющаяся основа | Конечное доказательство / остаток |
| --- | --- | --- | --- |
| N1 | Исходный rebuild-дефект различён от дефекта, возникшего после изменения | Диагностика элементов и postconditions операций | Собственная ограниченная модель с фактическим исходным дефектом и отдельный случай нового дефекта; независимый native readback ошибок до/после. Искусственное исключение Python или false stub не заменяет реальный rebuild-дефект |
| N2 | Известный сбой восстанавливает параметр или новую операцию; непроверенный эффект удерживается | Scalar restore, B1 owned inverses, durable unknown/holds | На итоговом wheel подтвердить scalar restoration и создание в конечном выпускаемом профиле; неопределённый случай сохраняет historical unknown, hold и запрет новой записи. Уже принятые случаи того же wheel использовать повторно по точному scope |
| N3 | Timeout ожидания сохраняет поздний результат; replay не выполняет запись второй раз | JobRunner/runtime и pure late/cancel/conflict tests | Публичный installed/native запрос с ограниченным ожиданием: дождаться того же operation_id и полного journal/postconditions, подтвердить единственный native dispatch; конфликт payload отвергается, отменяется только queued job |
| N4 | Перезапуск собственного сервера сохраняет unfinished→unknown и holds | JobStore recovery, ownership и application-hold pure tests | Отдельный installed server/process стенд: сначала доказать возврат CAD-вызова и отсутствие live COM, затем остановить только собственный сервер при незавершённом journal acknowledgement. Новый процесс с той же БД сохраняет unknown/hold; новая эпоха/reconnect не разрешают обход. Во время COM процесс не убивать |
| N5 | Reconciliation снимает лишь доказанный конкретный hold | Exact-scope reconciliation и независимые snapshot proofs | Независимое полное доказательство текущего поддержанного scope; explicit reconciliation не переписывает historical unknown в success. Проверить wrong scope/stale proof и область блокировки: application hold запрещает другие записи, document hold не разрешает нарушить общие session invariants |
| N6 | Пользователь получает раздельные timings и bounded приватную диагностику | `verify_timings_v2.py`, timing store/integration, исторический dev69 | Installed enabled/disabled/error gates плюс реальные интервалы из тех же N2/N3/N5 случаев: end-to-end, queue, доступные COM/rebuild/restore. Ошибка telemetry не меняет обязательный journal, исход задания и hold; отсутствующий интервал обозначается, а не выдумывается |

## Что исторические результаты не закрывают

[Приёмка dev69](DIAGNOSTICS_TIMINGS_ACCEPTANCE.md) подтверждает свой wheel,
metadata, двадцать фактических document reads и четыре внутренних базовых
случая. Restore/unknown и отказ timing storage там проверены pure. Она не
доказывает native late completion, restart или новые failure cases итогового
кандидата. `verifier_dimension_diagnostics.py` проверяет настройки/отчёт,
а не реализует restart/reconciliation acceptance.

Pure tests в `test_jobs.py`, `test_runtime_v2.py`,
`test_application_mutation_holds_v2.py` и `test_timing_integration_v2.py`
дают конкретные сценарии и ожидаемые состояния. Их результат не заменяет
фактический installed/native gate. Старый `verify_dimension_operations.py`
имеет контролируемое исключение после фактического setter; это не native COM
throw и не самостоятельное доказательство rebuild-дефекта.

## Порядок и граница

1. После B1/B2 собрать таблицу уже принятых точных same-wheel reports N2 и
   timings; не дублировать их физические операции без отдельного свойства.
2. Реализовать недостающую конечную оболочку N1/N3–N5 с exact fixture ownership,
   coherent journal и независимым baseline. Process recovery отдельно от COM:
   отсутствие живого вызова доказывается до остановки server-процесса.
3. Подготовить related pure проверки оболочки; итоговый wheel и installed gates
   выполнить по общему экономному процессу. Все native случаи последовательно
   проводит один владелец; реальные модели/БД/полные отчёты остаются в `work/`.
4. Принять B4 только по всем шести условиям, сохранности dirty соседа,
   собственному cleanup и восстановленной исходной сессии. Unknown нельзя
   автоматически повторить или признать success после закрытия документов.

Большие CAD-нагрузки, произвольные новые профили и общий benchmarking не входят
в этот конечный блок. Обязательные полнота checkpoint, pending/returned ledger,
reconciliation и native-постусловия сохраняются.
