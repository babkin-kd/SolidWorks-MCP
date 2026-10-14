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

Частичная installed-проверка N6 на exact dev96/f80ee6d выполнена без CAD.
`verify_timings_v2.py` без `--run-solidworks`: enabled/disabled, по20 metadata
измерений, доступны22 timing records при включении и0 при выключении;
SDK обеих сессий закрыт. `verify_timing_storage_fault.py` проверил отдельное
недоступное timing-хранилище: metadata и `job_not_found` сохранили результат,
`available=False`, `storage_failures>=1`, sample_count0; invalid filter отклонён.
Обязательный SQLite journal schema3 доступен, jobs0/mutations0, SDK закрыт.
Это принятые metadata-only installed gates, **не native N6/B4**. Проверка
изоляции telemetry при фактической mutation/restore/hold и реальные интервалы
N2/N3/N5 остаются открыты; искусственные или отсутствующие COM timings
не засчитываются.

На точном installed dev97/build49b899c повторены только обязательные
metadata-only gates нового wheel: enabled/disabled по20 запросов,22 actual
timing records при включении и0 при выключении, обе SDK-сессии закрыты.
Отдельный storage fault сохранил metadata/job_not_found/invalid-filter
контракт, available=false, storage_failures>=1, sample_count0; обязательный
journal schema3 остался доступен с jobs0/mutations0. Оба прогона normal exit0,
accepted=true в своём metadata-only scope, native_acceptance=false.
CAD не подключался; новые native mutation/restore/hold и реальные интервалы
N2/N3/N5 остаются открытыми. Полные receipts сохранены в private work/.

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

## Реализованная пассивная проверка restart — 12.10.2026

Добавлены `scripts/verifier_b4_recovery.py` и `tests/test_b4_recovery.py`, без
правок пакета, установленного wheel и helpers текущего B1. Предикат принимает
полные coherent before/after journal rows и фактически полученные blocker
observations. Проверяются полный набор job/request IDs, payload/digest, exact
checkpoint scope/native ledger, unfinished→unknown и prepared→unresolved,
сохранность terminal history, holds для другой цели и новой эпохи. Отдельно
виден conservative legacy-unbound fallback при отсутствии исходного checkpoint.

Связанные pure-проверки на настоящем JobStore/SQLite: **92 passed /3,59 с**,
включая62 новых B4 cases и30 существующих JobStore/application-hold cases.
CAD не вызывался. accepted относится только к journal receipt:
native_b4_accepted=false, process_stop_authorized=false,
cad_cleanup_authorized=false. Это не доказательство фактического native restart
и не разрешение остановить исполняющийся COM. Отдельные installed/native
прогоны и независимый quiescence proof до остановки своего сервера остаются.

Подготовлен отдельный `FinishBarrierStore` в `verifier_b4_finish_barrier.py`:
instance proxy для JobRunner, одно точное request/operation/payload finish после
возврата Python callback. Синхронно сохраняется полная coherent raw journal и
return result; running/prepared с committed verification и holds сохраняются
до явного release. Нет timeout, автоматически публикующего success, retry,
COM-вызовов, process stop или cleanup. Перед original finish проверяется весь
неизменный journal, не только target. Schema3/orphans/budget проверяются общим
пассивным reader. Ошибки persistence/verification/finish удерживаются.

Последний отдельный barrier-набор: **28 passed /1,12 с**; до safety-уточнения
shared reader/history был связан с92 core checks. Итоговая интеграция с новым
B3 reader: **89 passed /5,03 с**, наборы перекрываются. Барьер — подготовка N4,
не доказательство native quiescence: соответствующий флаг и разрешения на
остановку процесса/очистку остаются false. Следующий installed/native driver
должен получить независимый exact-scope proof до остановки своего сервера.
