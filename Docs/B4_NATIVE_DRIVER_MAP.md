# Конечная карта native-драйвера B4

Срез интерфейсов на 13.10.2026. Основание — шесть условий
[S1-B4](STAGE_1_BLOCK_ACCEPTANCE.md#s1-b4--диагностика-и-восстановление) и
[карта приёмки](B4_ACCEPTANCE_MAP.md). Это план недостающего драйвера, а не
отчёт приёмки. При первом составлении не запускались тесты; последующее
уточнение test-only process gate проверено только pure-тестами, как описано
ниже. CAD, процессы сервера, сборка и установка wheel не запускались.
Ни один native gate здесь не закрыт.

## Ограниченный профиль и конечные сценарии

Один владелец последовательно управляет SolidWorks и COM. Использовать только
собственные русские контрольные детали и сохранённый baseline открытой сессии,
включая dirty сосед, active/configuration, selection/view, preferences и файлы.
Цели, конфигурации, refs и ревизии задаются явно; после reconnect заново
адресуются по независимому native соответствию, старые opaque IDs не принимаются.
Минимальный профиль — уже выпускаемые самостоятельные writable part с одной
поддержанной конфигурацией, независимой driving length и B1 rectangle/extrusion.
Не расширять этот блок на произвольные зависимости, сборки или multi-config writes.

| ID | Конечный сценарий / допустимый результат | Обязательный реальный producer receipt |
| --- | --- | --- |
| B4-N1a | На своей fixture существует фактический исходный feature/rebuild-дефект. Dimension write отвергнут до записи; baseline сохранён | До запроса native tree/error codes/NeedsRebuild и геометрия; explicit request; нулевые native writes; exact failed/prewrite journal; независимый after. `DimensionCatalog._writable` отвергает `document_needs_rebuild` и `document_has_feature_errors`, а не разрешает редактировать дефектную модель |
| B4-N1b | На другой первоначально чистой своей fixture поддержанная запись создаёт реальный новый native дефект. Success запрещён; доказанное восстановление либо unknown/hold | Чистый before, фактические setter/rebuild returns и новая tree/error/geometry observation; outcome/restoration и независимый after. Не подменять дефект Python exception, stub `False` или собственным флагом |
| B4-N2a | Известное scoped восстановление driving length после контролируемого сбоя за фактическим setter | Same-wheel internal dimension report, actual setter/rebuild counts, полный before/after, `failed/rolled_back`, released execution guard, независимые extrema/volume/parameter и cleanup |
| B4-N2b | Известное удаление только своих вновь созданных B1 объектов после контролируемого отказа | Same-wheel B1 fault report и полный journal; `verified_rectangle_restoration`, exact созданные refs/ledger, исходный borrowed sketch и baseline; `controlled_python_fault=true`, `real_com_throw=false` |
| B4-N2c | Недоказанное наблюдение/восстановление не повышено в success, дальнейшая запись удержана | Фактическая native операция плюс конкретная контролируемая потеря подтверждения; `unknown/unresolved`, preserved before/ledger, blocker observations. Сбой после normal COM-return маркировать как Python/storage fault, а не COM throw |
| B4-N3 | Публичный installed/native запрос с `timeout_s=0` возвращает queued/running, затем тот же operation_id завершён. Replay возвращает тот же итог, conflict отказан; отмена только queued | Raw MCP response sequence и полный journal, exact request/payload/revision, счётчик одного native dispatch. Отдельные queued cancel и running cancel receipts доказывают отсутствие COM cancellation |
| B4-N4 | После возврата всех CAD-вызовов свой server-процесс завершён до terminal journal finish. Новый процесс на той же БД получает unknown/holds | Отдельные ownership/quiescence/stop receipts, finish barrier receipt, полные coherent before/after, все реальные hold queries; native process gate ниже |
| B4-N5 | Только независимое exact scope доказательство разрешает reconciliation конкретного unknown hold. History остаётся unknown | Свежее native scope proof с old→new mapping, baseline/effect/guard evidence, receipt доменного verifier, отдельный reconcile receipt и before/after journal. Wrong scope/stale proof отклоняются verifier до `reconcile_mutation` |
| B4-N6 | Enabled/disabled/error диагностика и реальные интервалы тех же принятых случаев; обязательный journal сохраняется при telemetry failure | Exact configuration, timing DB/report с limits/privacy, actual operation_id и phases; error receipt плюс неизменные outcome/hold/journal. Отсутствующие COM/rebuild/restoration интервалы помечены отсутствующими |

N1b требует заранее воспроизводимой реальной fixture в разрешённом профиле.
Если её нет или домен отвергает её раньше native записи, gate остаётся открыт;
не обходить validation и не засчитывать искусственную доменную ошибку.
Для N3 queued/running в первом response должно быть фактически наблюдено.
Завершение до первого response не доказывает late completion. Допустима
контролируемая задержка Python вне COM с честным обозначением; сам timeout
должен ограничивать ожидание, а не прерывать native вызов.

## Проверенные интерфейсы и повторное использование

| Интерфейс / helper | Что использовать | Граница доказательства |
| --- | --- | --- |
| `Runtime(store, worker_factory=..., catalog_factory=..., timings=...)`; `read/mutate(request_id, operation, arguments, timeout_s=...)` в `src/solidworks_mcp/runtime_v2.py:66,341` | Оболочка вокруг exact installed Runtime. Proxy store передать до первого dispatch; runner создаётся лениво в `_dispatch:347`. Durable context извлекается из arguments, поэтому payload барьера строится из реально записанного полного контракта | Нет специального finish barrier/restart/reconcile API. `_connection_epoch` новый после lazy catalog connect (`:118`), старые IDs не являются native mapping |
| `JobStore(path)` в `src/solidworks_mcp/jobs.py:101` | Единственный владелец private SQLite; открытие после подтверждённого выхода старого владельца запускает recovery (`:151`) | Второе открытие live БД нельзя использовать для наблюдения: оно пытается стать владельцем и изменить unfinished. OS-lock (`:68`) защищает от захвата, stale lock-файл не равен live owner |
| `prepare_mutation(..., before_state, effect_scope)`; `record_mutation_step(..., name, phase, evidence)`; `verify_mutation(..., outcome, evidence)` (`jobs.py:220,258,299`) | Домен создаёт checkpoint до первой записи, append-only pending/returned ledger и независимый итог | Pending/returned не снимают hold. Bare verified/result flag не заменяет domain postconditions. Pending step запрещает final verification |
| `mutation_blockers(connection_epoch, document_id, *, effect_scope='document')` (`jobs.py:201`) | Снять фактические полные blockers для каждого запроса `required_hold_queries` | Hold от другой эпохи блокирует все записи; application hold блокирует все документы даже в той же эпохе. Другой документ свободен лишь при document hold той же эпохи и отсутствии остальных blockers |
| `reconcile_mutation(operation_id, *, resolution, evidence)` (`jobs.py:323`) | Внутренний trusted domain вызов только после scope verifier; resolutions `accept_current_state` / `restored_before` | Метод проверяет transition unknown/unresolved и непустой dict, но не exact native scope, полноту или свежесть evidence. Production domain/public reconciliation entrypoint в текущем коде не найден |
| `JobRunner.wait` / `cancel` (`jobs.py:577,425`) | Poll SQLite после timeout; `cancel` выигрывает только queued→cancelled | Отмена wait не меняет native работу. Running cancel не поддерживается |
| `FinishBarrierStore(store, request_id, operation, payload, persist)` в `scripts/verifier_b4_finish_barrier.py:67` | One-shot proxy exact успешного finish; `wait_reached`, `receipt`, явный `release` | Только Python barrier; все permission/native flags false. Matching status должен быть running/prepared, committed verification с evidence и `result.verified is True`. Config constructor требует непустую строку |
| `read_journal` в `scripts/verifier_lifecycle.py:205` | Raw coherent mode=ro snapshot jobs+mutations с digest, schema3, WAL, полным bounded набором и orphan check | Public `job_get/list` DTO не содержат digest и не заменяют raw snapshot; нельзя выбирать только target rows |
| `required_hold_queries` / `validate_restart_receipts` в `scripts/verifier_b4_recovery.py:101,122` | До restart вычислить конечный набор old/new epoch × target/other × document/application. После startup реально вызвать blocker queries, затем валидировать | Обязательно unfinished mutation; никакого нового job/ledger в before→after окне. `accepted=true` только journal proof; native/process/cleanup flags false |
| `VerifierSupervisor`, `open_supervised_session` в `scripts/verifier_lifecycle.py:233,591` | Обычные public N2/N3/N6: tracked request, drain, protocol/journal и cleanup decision | Running barrier не пройдёт обычный drain. `history_seed` только после safe drain; `readonly_restart=True` не принимает произвольную историю и не предназначен для N4 recovered unknown |
| `verify_dimension_operations.py:110`, `verify_dimension_mcp.py:181` | Same-wheel typed setter/scalar restoration, independent native box readback; public wait/replay transport helpers `:114–142` | Injection за normal setter — controlled Python fault. Не доказательство native COM throw, N1 или незавершённого process restart |
| `verifier_rectangle_stages.py:40`, `verifier_rectangle_restoration.py:18`, `verifier_rectangle_internal_acceptance.py:191` | Exact committed/restored rectangle predicates и same-wheel B1 reports | Не заменяют независимую native observation и ownership/cleanup данного B4 process стенда |
| `verify_installed_metadata.py:21,42`, `verify_timings_v2.py:36`, `verifier_dimension_diagnostics.py:24,55` | Installed identity/schema, enabled/disabled diagnostics, preferences preservation | Timings verifier native branch делает reads, не доказывает native restore/restart/telemetry failure B4 |

Строки указывают проверенный срез, а не стабильные API идентификаторы.
Связанные тесты `tests/test_b4_recovery.py` и `tests/test_b4_finish_barrier.py`
используют настоящие JobStore/SQLite и Python threads, без native acceptance.
Их fixtures manually создают checkpoints/evidence: переносить это как native
producer нельзя. Проверки persistence latch, exact payload, whole-history
immutability, async callback rejection и recovery использовать для разработки
драйвера, сохраняя различие pure / installed / actual CAD.

## N4: последовательность и конкретный process gate

1. Создать отдельный принадлежащий проверке child server на exact dev-wheel,
   private `work/` state root и свежей БД. Сохранить wheel SHA256, installed
   module/entrypoint/source identity, helper hashes, own PID/creation identity,
   command/env и путь БД. `PYTHONPATH` исходников исключить. Рабочий v1 и
   пользовательские документы не включать в process ownership.
2. Предварительно выбрать один finite operation профиль. Для полного native
   step ledger предпочтителен уже поддержанный B1 rectangle/extrusion;
   scalar dimension допустим лишь с отдельным честным producer return proof.
   Не вставлять фиктивные ledger events в production checkpoint.
3. До первого Runtime dispatch установить instance `FinishBarrierStore`.
   Синхронный `persist` пишет отдельный private receipt полностью и подтверждает
   durable запись; ошибка/неполнота не даёт `wait_reached=True`. Payload включает
   точные arguments/context/mutates, operation и request_id, а не только dimension.
4. Зафиксировать admission: после выбранной операции не посылать новые CAD jobs,
   включая getters/cleanup. Дождаться точного persisted barrier, сохранив
   running/prepared, committed verification и return result. Barrier стоит
   внутри `JobRunner._execute` после callback/verify и до terminal finish.
5. **Gate B4-N4-Q:** нужен независимый owner producer, подтверждающий normal
   return полного native callback, возврат всех его вложенных CAD/restore/UI
   действий и отсутствие иных live/queued CAD-вызовов при закрытом admission.
   Он связывает request/operation/target/revision и chronology с барьером,
   проверяет exact ledger (если operation его имеет), independently observed
   postconditions и released guard. Сам barrier flag, status running,
   `result.verified`, отсутствие pending в ledger или timeout недостаточны.
   Запись quiescence proof отдельна от helper receipt: его false flags не менять.
6. В отдельном observer сохранить `before=read_journal(path)` и сверить весь
   набор с `barrier.receipt['journal']`, включая terminal history. Подготовить
   distinct other_document probe. Не создавать jobs до завершения after snapshot.
7. **Gate B4-N4-P:** pure command gate подготовлен ниже, но helpers пока
   не реализуют фактический controlled child exit при
   удержанном finish. `release()` завершит исходный job; это control path,
   не crash recovery. Без release STA ждёт бесконечно внутри Python finish.
   `Runtime.shutdown` ставит `_release_catalog` за барьером, а
   `JobRunner.shutdown` закрывает store лишь после остановки worker. Поэтому
   ordinary shutdown не обеспечивает unfinished restart. Нужен отдельно
   разработанный test-only child lifecycle с подтверждённой own process
   identity, owner-issued exit command после Q и явным exit receipt до нового
   старта. Нельзя заменить его SDK timeout/terminate fallback, ручным close
   underlying store при waiting worker или процессным kill по истечении времени.
   Пока Q или P не реализован и не доказан, N4 остановлен перед process stop.
8. Только после Q+P и фактического выхода прежнего owned child запустить новый
   child на том же установленном wheel и неизменной БД. Не удалять SQLite/WAL/
   lock, не переписывать rows и не переносить synthetic database.
9. Немедленно получить полный `after`; ожидаются queued/running→unknown,
   `runtime_restarted`, prepared→unresolved. Scope/before-state/verification/
   pending-returned ledger и terminal history сохраняются. Отсутствующий
   checkpoint получает conservative `legacy-unbound`, а не выдуманный scope.
10. Получить новый actual connection epoch после контролируемого reconnect;
    отдельные CAD discovery jobs для этого выполнять после фиксированного
    recovery window. Само окно before→after не расширять новым journal.
    Полные blocker queries выполнять в live новом store и записать exact
    results для `required_hold_queries`; затем `validate_restart_receipts`.
    Если reconnect меняет журнал, сравнивать recovery snapshot до discovery,
    а blocker receipts — с теми же неизменными recovered checkpoints.
11. После пассивной валидации в отдельном окне проверить same-request replay
    без dispatch, changed-payload `request_conflict`, новый request и epoch
    без обхода hold. Сохранить новый полный journal; не подавать его как `after`
    прежнего finite recovery окна.
12. Перейти к N5 exact reconciliation и только затем рассматривать cleanup.
    Не повторять uncertain mutation, чтобы узнать её результат.

При провале Q/P или утрате acknowledgement: retain own fixtures/journal,
сохранить конкретную причину и evidence; native/restart/cleanup acceptance false.
Задержка наблюдения остаётся задержкой, неизвестный исход не становится success.

## N5, cleanup и acceptance

N5-драйверу недостаёт trusted scope verifier. Он должен на своём STA независимо
снять native current state всего affected scope и application invariants,
сопоставить old checkpoint с exact новым document/config/object mapping,
проверить свежесть revision/event boundary и доказать либо текущий разрешённый
effect (`accept_current_state`), либо полный before (`restored_before`). Другой
document/configuration, частичный before-state, stale proof, unresolved native
step или неосвобождённый guard отклоняются до store call. Bare dict evidence
для `JobStore.reconcile_mutation` не считается таким verifier.

Reconciliation вызывает store ровно для доказанного operation_id; phase становится
reconciled, historical job остаётся unknown, исходный result/error сохраняется.
Проверить повторный вызов, другие holds и все blockers after. Same-epoch
document hold допускает другой target только при отсутствии application holds;
новая эпоха сама по себе все старые holds консервативно расширяет на записи.
Текущие dimension/B1 guarded mutations имеют application scope, поэтому
изолированный document-hold пример из JobStore tests считать pure, пока не
выбран фактический native producer такого scope. Не ослаблять production scope.

Обычный `VerifierSupervisor`/`InlineFixtureCleanupGate` сохраняет unknown fixtures;
отдельное reconciliation cleanup решение нельзя получить изменением historical
status или ручным выставлением gate. После N5 нужен explicit exact-scope
cleanup proof: все native calls returned, новые writes закрыты, holds reconciled,
own document identities достоверны, UI/preferences released, независимое
состояние соседей/файлов совпадает с baseline. Закрывать без сохранения только
свои контрольные документы; затем независимо проверить census, active state,
dirty/selection/view/preferences и нетронутые пользовательские файлы. Закрытие
модели само по себе не является reconciliation неизвестного эффекта.

N6 использует те же принятые operation_id: total elapsed/end-to-end, queue,
измеренные COM/rebuild/restoration и transport await. Phases из
`timings_v2.PHASES` inclusive/nested, их не складывать в total; crash до trace
finish может оставить timing record отсутствующим. Bounded limits действуют
в пределах `TimingConfig` (records 1–10000, days 1–31, bytes 1–64 MiB).
Timing DB не должна содержать CAD payload/paths/secrets. Error-mode инъекция
только в optional recorder на own стенде; mandatory JobStore не отключается,
полный журнал и outcome/hold до/после проверяются независимо.

Итоговый private manifest перечисляет N1–N6, exact wheel и helper hashes,
request/operation IDs, producer receipts, installed metadata/schema, native
effects, независимые proofs и cleanup. Same-wheel B1/B2 evidence переиспользовать
только по точному принятому scope, без повторения физического сценария ради
числа тестов. Непроверенные N1 fixture, N4 Q/P, N5 verifier и N6 native error
gate остаются отдельными открытыми строками. B4 accepted только при всех шести
условиях и восстановленном baseline; skipped/unknown не считаются passed.
Полные CAD-модели, DB, process receipts и отчёты сохраняются в private `work/`,
в публичный Git попадают лишь обезличенные результаты и этот контракт.

## Test-only gate B4-N4-P — 13.10.2026

Добавлены `scripts/verifier_b4_process_exit.py` и
`tests/test_b4_process_exit.py`. `OwnedChildExitGate` работает с реальными
`FinishBarrierStore.state/receipt/wait_reached/path`, а не с выдуманным полем
`callback_returned`: у barrier имеется `python_finish_intercepted`, все native
permission flags остаются false. Сохраняются exact running/prepared с committed
verification, result, payload digest и полный coherent journal из read-only reader.

Gate фиксирует собственный `os.getpid()` и свежий incarnation token, генерирует
одноразовый nonce; внешний PID/identity constructor не принимает. Command
связан с process identity, operation/request, durable job digest, SHA256 всего
журнала, barrier receipt и Q proof. Другой gate того же PID, изменённый nonce,
тайм-аут вместо команды, смена scope/history или released barrier запрещают
callback; ошибки и повтор команды latch без retry. Введённый incarnation token
идентифицирует этот gate в own child; native wrapper ещё должен доказать своё
server ownership и фактический OS exit, токен не является OS process-start receipt.

`observe_owner_q(binding)` — отдельная trusted зависимость test-owner harness,
не MCP input. Её helper-owned schema требует явные normal callback return,
all native calls returned, completed/released guard и закрытый admission;
live/pending/queued/unknown запрещены строгими bool checks в flags и вложенных
observations. Actual callback/guard/admission receipts обязательны. Сам Python
validator проверяет контракт и binding, но не может доказать истинность этих
native observations. Synthetic Q в tests честно обозначен pure и не переносится
как native producer. Отсутствующий или полностью returned ledger без отдельного
Q доказательства недостаточен.

Q и весь binding повторно проверяются при issue, перед persistence и после
синхронного durable exit intent, непосредственно перед единственным injected
`exit_callback(receipt)`. Owner wrapper обязан эксклюзивно держать admission
закрытым и barrier unreleased до callback; helper не блокирует чужой код от
release. Deferred callbacks, persistence failure, изменение Q во время записи
intent и callback exception не дают retry. Normal test callback return отражён
только в detached in-memory receipt, не является process exit observation.

Нет `os._exit`, kill/terminate, COM, timeout-stop или автоматического release.
Все результаты содержат `accepted=false`, `process_stop_authorized=false`,
`native_b4_accepted=false`, `native_restart_proven=false`,
`native_dispatch_proven=false`, `cad_cleanup_authorized=false` и
`process_exit_observed=false`. `exit_command_validated=true` означает только
проверенный вызов trusted injected callback по этому test контракту.

Связанный новый pure-набор: **89 passed /2,79 с** на реальных SQLite/JobStore и
Python finish barrier, без CAD или process exit. Использован отдельный свежий
basetemp `work/pytest-b4-exit-agent-*` и source `PYTHONPATH=src` только для pure
разработки; это не installed-wheel acceptance. Предыдущая sandbox попытка
упёрлась в Windows `PermissionError` pytest temp ACL и не засчитывалась.
Повтор выполнен с разрешённым unsandboxed shell и новым basetemp, без удаления
старых каталогов. Production/wheel/версии не менялись.

Остаток P: native owner-issued Q интеграция и реальный own-child exit protocol
с последующим OS exit receipt. Без них запуск restart всё ещё запрещён;
pure команды и intent receipts не закрывают Q/P или native B4.

## CAD-free own-child protocol — 14.10.2026

Добавлены `scripts/verifier_b4_owned_child_process.py` и отдельные тесты.
Фиксированный synthetic entrypoint создаёт реальный JobStore/SQLite,
FinishBarrierStore и OwnedChildExitGate. Родитель удерживает исходный Popen
handle, наблюдённое OS-время старта, nonce и helper hashes. Единственная команда
передаётся исходному процессу через stdin; текущий child вызывает os._exit
только после gate и durable intent/callback receipts. Родитель сверяет actual
OS exit code с этими квитанциями. Нормальный callback return/exit0, чужие
команда/identity, неполные квитанции и failed intent не принимаются как gate exit.
Timeout сохраняет живой owner и не вызывает остановку или повтор команды.

Ошибка после успешного Popen сохраняет exact handle через
OwnedChildLaunchError.retained_owner. Одно новое наблюдение original handle/start
и отдельная recovery receipt позволяют продолжить именно этот synthetic
протокол; partial original launch receipt и исходная ошибка сохраняются.
Неудачное повторное наблюдение удерживает owner, без kill/adoption/relaunch.

Windows venv python.exe оказался redirector с отличающимся child PID.
Для этого source-only эксперимента используется прямой sys._base_executable
с pure dependencies. Это не запуск exact installed-wheel CAD server.
Все Q receipts явно synthetic_cad_free; native_q=not_run, native B4/restart/
dispatch acceptance и cleanup/process-stop authority остаются false.

Root integration: **211 pure passed /11,60 с**, normal exit0, отдельный внешний
basetemp; тесты запускают и завершают только собственные synthetic Python
children. COM/CAD и текущий N5 не затронуты. Остаток P теперь состоит в
интеграции с actual installed server launch/owner, а Q — в действительном
producer proof полного возврата native callback/guard и закрытого admission.
Synthetic process protocol не закрывает эти native требования.

В чистом CI745502e own-child readiness завершилась отказом (21 failures,
4 teardown errors). Локальные211 related/full11271 остаются доказательством
своего source окружения, не переносимым результатом CI. Проверяется запуск
child при editable-install без PYTHONPATH; strict handle/start/nonce gates
не ослабляются. До воспроизведения и исправления переносимость стенда открыта.

Launcher теперь передаёт первым корень фактически импортированного parent
package (resolved __file__) и связывает его с child identity. Direct-base
Python запускается с -S, зависимости передаются явно; наследуемые base/user
.pth не выполняются. Отдельный normally returned import control доказал,
что PYTHONPATH с empty editable site не обрабатывает находящийся там .pth;
исправленный own-child прошёл в том же окружении и с foreign cwd.
Historical CI причина без child stderr остаётся гипотезой, а не доказанным фактом.

После actual terminal poll ошибка before-ready включает exit code и не более
4096 байт stderr tail. Timeout по-прежнему не доказывает exit и ничего не
останавливает. Root gates/process/recovery integration без PYTHONPATH:
**214 pure passed /11,72 с**, normal exit0, все synthetic children terminal,
без CAD. Exact handle/start/nonce и native_false gates сохранены. Итоговый
source/CI-кандидат этого исправления ещё должен пройти общий checkpoint.

Финальный source34ccab5 full pure принят11274/323 CAD deselected /478,61 с,
normal exit0. Remote CI38495337250/job115629709085 на eaf5e5b завершился
success: unit11274/323 deselected /979,00 с, lock/build/isolated install и
metadata83 passed без CAD. Native B4 по-прежнему not_run; source-only
переносимость подтверждена этим CI, actual Q/server/restart gates остаются.

## Installed metadata launcher — подготовка 14.10.2026

Новые отдельные scripts/verifier_b4_installed_child.py и tests поддерживают
fixed direct-base child, original Popen handle/start/nonce, exact installed
wheel/build/package/SDK и собственный metadata-only transport. SDK stdio_client
не используется: его timeout shutdown может terminate/kill процесс.
Normal EOF/server_v2.main return/exit0/complete empty journal — отдельное
доказательство lifecycle; native Q/recovery/restart/reconciliation остаются not_run.

Related71 pure passed/5,38 с без actual installed server/CAD. Root actual
attempt1 на dev97 завершился failed до импорта entrypoint: -S не добавил
pywin32 paths, ModuleNotFoundError: pywintypes. Child-ready был записан слишком
рано. Отдельный read-only audit подтвердил, что исходный child уже завершён
и server/jobs.sqlite не создан; CAD/job calls не было. Исходный failed report
сохранён. Исправляются explicit installed Windows dependencies и ready ordering;
actual launch/close этим ещё не принят. Текущий B2 native owner не затронут.

Attempt2 actual installed server/SDK metadata и normal EOF/exit0 прошли, но
post-exit collector failed: sibling import не зарегистрировал модуль для
dataclasses. Отдельный root audit подтвердил sdk_closed/eof_sent, точный
normal-server-return identity, exit0,83 tools и пустой journal; исходный
failed receipt оставлен failed, lifecycle gate им не принят.

После explicit anchored pywin32 paths/DLL module-file hashes и исправления
sibling registration — related90 pure passed/5,56 с. Ready публикуется после
импорта реального entrypoint, .pth/user site не выполняются; при import failure
старый module binding восстанавливается. Helpers зафиксированы до integration.

Fresh attempt3 на exact installed dev97 завершился normal exit0:
metadata_process_passed=true,83 tools, exact original PID/start/nonce/wheel/
package/SDK/Windows dependency identity, normal server_v2.main return, SDK
close/EOF, фактический exit0 и complete actual journal=[] подтверждены.
CAD/job calls=[]; SolidWorks не подключался. **Принят только metadata-only
launch/close bridge.** Native Q, controlled unfinished exit, recovery/restart
и reconciliation всё ещё not_run; B4-N4/общий B4 этим не закрываются.
