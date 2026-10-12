# Первое сохранение L3 — промежуточная контрольная точка

## Текущее состояние dev89

L3 открыт. Ограниченная явная активация S1-B5-ACT уже принята на dev89,
включая четыре внутренних случая и public MCP/native. Saved-file интеграция
L3-P1 ещё не принята. [Контракт активации](NATIVE_PART_ACTIVATION.md).

Положительная installed **L3-I1 dev89 прошла за980,22 с**, terminal/exit0:
`work/native-first-save-dev89-positive-1/report.json`, без source PYTHONPATH.
Exact wheel Git ea93a0b7d9d0b63408539d7a3f91f889eca38034, metadata75/23 и все
текущие helper hashes подтверждены. Actual job succeeded/committed и detached
predicate проверены; 131 capture returned, independent full readback/mapping41,
replay без нового вызова, own cleanup/empty baseline и non-STL preferences приняты.
SHA256 отчёта: `3c99c999d11ff82037a0281fa76dee0b88fb39c777f66602f13762d7fbcae05a`.
`positive_case_passed=true`, **accepted=false**: только I1, не весь L3.

Installed **L3-I2 dev89 прошла за685,28 с**, terminal/exit0:
`work/native-first-save-dev89-rejections-1/report.json`. Existing destination
и real rename-induced stale revision отказали до записи: Copy0, failed без
mutation; прежний файл сохранён. Все три finite labels пройдены, 16 captures
returned, own cleanup/empty baseline и current helper hashes подтверждены.
SHA256 отчёта: `5a09f2bf47278f70e7e78b0e822005e8ae07711330443a7c8d4cfb94c178d235`.
`rejection_cases_passed=true`, **accepted=false**: не whole L3.

Installed **L3-I3 dev89 прошла за868,76 с**, terminal/exit0:
`work/native-first-save-dev89-race-1/report.json`. Actual destination race
после Copy/readback не перезаписала чужой файл; job failed/rolled_back,
detached actual race predicate и replay подтверждены. Native counts:
Copy1/open1/close1/publication1; source/neighbor и foreign bytes/identity
сохранены. 91 captures returned, own cleanup/empty baseline/current hashes
подтверждены; принадлежащий проверке пустой stage учтён, whole L3 не принят.
SHA256 отчёта: `3cd463a3ebcf69abe16aacf1af7e7ca59eb1ae4c1ac266ec47c86279cb432e50`.

Installed **L3-I4 warning_after_copy dev89 прошёл за757,18 с**, terminal/exit0:
`work/native-first-save-dev89-fault-warning-1/report.json`. Original native
Copy вернулся нормально, success=true/errors0/warnings0; затем управляемый
ответ моста дал unknown/unresolved, hold/replay без повторного Copy.
Independent clone41/readback и exact own reconciliation/empty baseline приняты;
исторический статус остался unknown, phase=reconciled. 42 captures returned,
current helper hashes и exact dev89 подтверждены. Это не actual native warning.
SHA256 отчёта: `b3449519da41411a2910cb9c3b7c64c6d7c9990b5fbcf869c751aebcca0a5872`.
False/throw/incomplete и публичный L3-P1 оставались на момент этой контрольной
точки; actual false-прогон описан ниже. Весь I4/L3 не принят.

Оставшиеся false/throw/incomplete подготовлены как private последовательная
очередь в ignored work/. Контроллер не вызывает COM и не очищает модели:
каждый отдельный native-owner запускается только после exit0 и terminal
предыдущего отчёта с current hashes/exact wheel, owned=[], restored baseline,
normal original Copy и доказанным unknown→reconciled без смены исторического
исхода на success. Live/pending/retained/несовпадение останавливает переход;
нет timeout/kill/automatic retry. После всех трёх выполнится общий detached
gate семи отчётов dev89; он не заменяет public L3-P1.
Управляющий guard проверен на искусственных данных: допустимый baseline и
12 unsafe отказов, без COM/дочерних процессов. Это не native-приёмка I4.
После terminal warning/exit0 и проверки его фактического отчёта очередь
запущена. **False_after_copy dev89 прошёл752,30 с**, terminal/exit0: current
helpers/exact wheel, original normal Copy, unknown/hold/replay, clone41,
reconciliation/empty baseline и 42 returned captures подтверждены отдельно.
SHA256: `180b5ab74f9201622d862d4effae4864b09213000aaeaec3dfceea27c4b97a39`.
**Throw_after_copy dev89 прошёл755,45 с**, 42 captures returned:
SHA256 `2a14d3f0320ce411fa843c327b1f29e755fde2ff33c854b813ce1303f811c19d`.
**Incomplete_after_copy dev89 прошёл721,84 с**, 30 captures returned:
SHA256 `0cfd20137db8683bd29c557c78bb621324efb84e3882a5b903deb72cde762e01`.
Оба terminal/exit0, original normal Copy, unknown/hold/replay, independent
clone41 и exact reconciliation/empty baseline подтверждены; historical
unknown сохранён. Полная очередь terminal/exit0; **общий detached gate всех
семи dev89-отчётов прошёл** с trusted current helpers/exact wheel/metadata75.
Root отдельно повторно проверил gate и фактические terminal fault proofs.

После этого запущен **публичный L3-P1** в
`work/native-first-save-dev89-public-1/` на том же installed dev89, без source
PYTHONPATH. Один новый CAD-владелец; internal gate и четыре ACT-отчёта
проверены до CAD. Public-chain acceptance ещё не получен, L3 не закрыт.
Private модели/контроллер/отчёты остаются вне Git; отдельного push/CI нет.

Для публичного L3-P1 обязательны внутренние свидетельства этого же wheel.
Следующие записи dev88 сохраняют историю, не являются приёмкой dev89.

## История dev88

L3 **не принят**. Два публичных инструмента входят в установленный dev88;
metadata/stdio accepted73 tools/22 mutations, source pure5978/323 CAD deselected.
Installed L3-I1 прошёл (1008,63 с): committed, 24 ledger rows verified,
independent full readback/mapping41, own cleanup/baseline. Whole L3 не принят;
installed L3-I2 прошёл (686,00 с): existing/stale до записи, Copy0, cleanup/baseline.
L3-I3 прошёл (874,27 с): actual no-replace collision, known rollback, foreign bytes/identity,
replay и cleanup/baseline. Installed L3-I4 warning_after_copy прошёл (757,28 с): unknown/hold/replay,
independent clone/readback и exact own reconciliation, historical unknown сохранён.
L3-I4 false_after_copy прошёл (756,52 с): unknown/hold/replay, independent clone41
и exact own reconciliation/baseline. Throw_after_copy прошёл (757,30 с): unknown/hold/replay, clone41, source/neighbor/stage
preservation, cleanup/baseline и reconciliation; historical unknown сохранён.
Incomplete_after_copy прошёл (726,39 с): original normal Copy, controlled
incomplete receipt, unknown/hold/replay, independent clone41, reconciliation
и baseline. 12.10.2026 общий detached preflight семи внутренних отчётов
одного dev88 с текущими helper hashes прошёл; public/S1-B5-ACT остаются.
Для полного open→edit MCP-сценария выявлен S1-B5-ACT: explicit active part
ещё не реализован, ручная test-owner activation не закрывает этот остаток.
[Точный артефакт и проверенные факты dev88](CHECKPOINT_DEV88.md).
Приёмка открытия dev87 относится к своему точному артефакту;
новые исходники не наследуют её автоматически.

**Текущий source domain probe2 прошёл**, 994,58 с: job succeeded/committed,
отдельный протокольный predicate подтвердил 24 native ledger rows. Полное
независимое CAD-чтение подтвердило clone/mapping (41 роль), writable final,
неизменность dirty соседа; собственные документы закрыты, baseline/CWD/non-STL
восстановлены, owned=[], native_calls_live=false. Это положительная source-проба,
а не installed/internal/public gate L3. SHA256 окончательного отчёта:
`4b1648f9e2670ec054df8640080823dfdd798113b7fe073ddf0802c19da8fbe1`.
Частные артефакты: `work/native-first-save-domain-probe-2/report.json`,
`protocol-check.json`, `oracle-captures/`. Прежний unknown остаётся unknown;
успех нового задания не устанавливает задним числом причину прежнего расхождения.

Полный source domain probe1 завершился **unknown**, 988,76 с: native Copy,
stage read/close, публикация, final open и source close вернулись нормально,
но полное постусловие после retirement не совпало. Первоначальный журнал не
сохранил точный несовпавший снимок, поэтому причина ещё не установлена.
Независимое чтение затем подтвердило неизменные bytes/identity, полный clone
state и dirty сосед; текущим активным документом оказался сосед. Сравнение
durable JSON с live tuple-массивами в диагностике потребовало канонической формы;
это свидетельство дефекта представления, а не доказательство причины всего отказа.
Own cleanup выполнен, пустой baseline/CWD/non-STL independently accepted;
failed отчёты и unknown-job не переписаны. Keeper остановлен лишь после
проверенных terminal native receipts и подтверждения пустой сессии.

В исходниках исправлена граница snapshot→durable JSON, clone equality сохраняет
различие bool/int. Добавлена отдельная однократная активация exact final после
source close, если SW активировал соседа; до активации все данные/файлы/окна
по-прежнему должны совпасть. При любом mismatch journal сохраняет полный
before/observed до выхода guard, без автоматического повтора/cleanup.
Связанный набор с внешним protocol gate:278 passed,20,23 с. Это искусственные
проверки, не CAD-приёмка. Source probe2 запущен на новых собственных фикстурах;
running не считается passed, результаты старого unknown не переносятся.

Пользовательский результат и конечные gates остаются в
[приёмке блоков](STAGE_1_BLOCK_ACCEPTANCE.md). Три стадии и расширения D2/D3
сохранены. Здесь фиксируется продвижение реализации, а не новый выпуск.

## Подготовленный код

- One-shot мост modern `IModelDocExtension.SaveAs3` Silent|Copy: точный active
  unsaved source/configuration, пустое выделение, receipt до вызова, строгий ACK,
  без автоматического повтора. Close bridge не читает retired COM после CloseDoc.
- Доменная составная операция: staging → copy → независимое открытие staging →
  закрытие reader → публикация без overwrite → открытие final → проверка →
  retirement исходного документа → последним native-шагом возврат CWD.
  Неопределённый исход сохраняет source/artifact и application hold.
- Пассивный oracle-кандидат для простого прямоугольного основания: полный
  аналитический BREP, feature graph, размеры и линейные связи эскиза, параметры
  blind extrusion, плоскости, единицы, свойства и материалы, полный реестр
  поддержанных размерных аннотаций. Body/face/edge роли связываются с полной
  аналитической incidence, а не порядком перечисления. PID переносится в явную
  bijection только после exact native roundtrip.
- Первое основание v2 создаётся в пустой детали без области воздействия на
  существующие тела: FeatureScope=False. Данные этого режима проверены в
  source-прототипе; это изменение ещё не принято на новом установленном wheel.
  Active FeatureScope требует другого полного inventory и остаётся unsupported
  до записи. Ни один активный параметр не исключается ради прохождения Copy.
- Размерные роли width/height/depth выводятся из полностью проверенных связей
  прямоугольника и native anchors. Полные имена проверяются по своему владельцу
  и документу; исходные qualified имена сохраняются в native_observations.
  Не имеющий смысла при отключённом FeatureScope getter AutoSelect тоже остаётся
  в полном source checkpoint, отдельно от persisted semantic state. Неизвестные
  observation-поля, чужой владелец и изменение доступного control отвергаются.

Полный passive source capture проверен на двух собственных реальных деталях:
два последовательных снимка каждой совпали, metadata сохранилась. Учтены
служебные данные проверенного шаблона, closing proof конфигурации/объектов
и native event envelope. Последующие source-прототипы подтвердили clone capture,
перенос ссылок и совместимость нормального CAD/NTFS-прохода, как указано ниже.
Полный доменный протокол с журналом/UI guards, интеграция и MCP-фасад ещё
не приняты native; runtime и MCP-фасад уже подключены и проверены pure.
Exact installed/native приёмка остаётся обязательной.

Начальный source — видимая активная unsaved part с одной конфигурацией, одним
solid и одним окном; профиль — независимое прямоугольное blind основание.
Baseline допускает видимые self-contained parts того же наблюдаемого профиля.
Сложные модели, скрытые документы, ссылки и связанные/evaluated свойства
отклоняются до записи. Их поддержка остаётся в D2-GEOMETRY/D2-DOCUMENTS/D2-CONFIG,
а не объявляется выполненной. Пустой selection обязателен для source;
соседний документ наблюдается полностью.

## Полученные свидетельства

| Проверка | Фактический результат | Что подтверждает |
| --- | --- | --- |
| Dev88: preflight/protocol/metadata source-набор | 40 passed, 6,25 с | Новый installed L3-I1 wrapper проверяет wheel/origin/catalog до CAD; отклоняет неверные preflight gates. Core общий с source-пробой, partial positive report не объявляет весь L3 принятым |
| Dev88: итоговый полный source pure-набор | 5978 passed, 323 CAD deselected, 99,46 с | Версии pyproject/package/lock/registry template согласованы. Первый dev88 full-набор имел один packaging failure из-за старого template dev87 (5977 passed); исправление проверено повторным полным набором. Native не запускался |
| Full source domain probe2 | passed, 994,58 с; job committed, 24 protocol rows verified, independent full readback=true, mapping41, cleanup/baseline=true | Первый успешный полный source-протокол с actual CAD/NTFS, UI guards и durable журналом. Не новый wheel; stale/race/negative cases и public MCP-приёмка L3 ещё не завершены |
| Текущий source metadata/runtime/MCP-набор | 44 passed, 4,56 с | Installed verifier ожидает реализованные 73 tools/22 mutations, включая два first-save tools и их scope; прежний каталог без L3 отвергается. Проверка искусственная/source, без CAD и нового wheel. Первая попытка остановилась на collection из-за импорта установленного dev87 вместо src, затем исправлен PYTHONPATH |
| Текущий полный source pure-набор | 5973 passed, 323 CAD deselected, 99,38 с | Штатный фильтр `not solidworks`, без `--run-solidworks`; source PYTHONPATH указан явно. Не является installed metadata или native-приёмкой. Подробный журнал: ignored `work/pytest-first-save-full-2.log` |
| Связанный source pure-набор, итог прототипа | 255 passed, 12,76 с | Мост, доменный протокол с искусственным CAD/FS, файловые receipt и NT-фаза публикации, пассивная классификация rectangle; native не запускался |
| Последующий связанный source pure-набор | 419 passed, 13,03 с | Дополнительно actual QueryInterface helper на fake COM, составные dimension/annotation anchors, native-plane PID нормализация и целый capture на искусственной модели. Это не новый wheel и не CAD-приёмка |
| Whole passive source probe 3 | Обе реальные собственные детали: два совпавших capture каждой; metadata_unchanged=true; 174,78 и 173,51 с | Полное чтение заявленного исходного профиля, шаблонных служебных данных и PID roundtrip. Только source-прототип, без SaveAs/clone/disk/readback или installed gate |
| Source oracle probe 1 и промежуточные passive probes | Отказы сохранены | Первый отказ до SaveAs из-за неполного учёта шаблона; последующие выявили различия raw PID/IFeature/IAnnotation interfaces. Финальный source capture не переписывает их в passed |
| Source oracle Copy probe 2 | failed; Copy вернул True/0/0, reader открылся с0/0, source/dirty сосед сохранены; clone equivalence не прошёл | На legacy-основании FeatureScope=True активный AutoSelect изменился True→False. Это не допустимая квалификация имени и не исключённый control; результат не принят. Три terminal own модели закрыты по полным прежним raw snapshots, CWD и non-STL baseline восстановлены отдельно; failed сохранён |
| Связанный source-набор после dimension roles/base controls | 289 passed, 11,98 с | Поддержанный namespace mapping, native owner/role связь, отказ active scope/unknown fields/foreign owner/изменения параметров, домен first save и базового построения. Без CAD/wheel |
| Source oracle Copy probe 3 | passed, 35,15 с; source/clone полный proof и41 mappings; own cleanup/baseline=true, pending=false, owned=[] | Свежие фикстуры созданы actual v2 builder; FeatureScope=False. Новый Copy True/0/0, независимый read-only native reader0/0; исходник/dirty сосед и staged bytes сохранены, reader roundtrip/CWD/cleanup проверены. Только source experiment; native_first_save_accepted=false, exact_installed_acceptance=false |
| Source CAD/NTFS prototype 1 | passed, 44,28 с; cad_protocol_steps_verified=true, filesystem_lease_released=true; baseline=true, pending=false, owned=[] | Modern Copy и независимый reader работают при строгих directory leases; no-replace публикация, открытие final для записи, полный oracle/41 mappings, retirement source и terminal own cleanup подтверждены совместно. SHA256 отчёта `b620a51b2ed4b91a3e4c03a8d327e2e19bb0fde4fa63289766d620cb4b8b8646`. Source experiment: native_first_save_accepted=false, exact_installed_acceptance=false; полный доменный журнал/UI guards и MCP не приняты |
| Связанный source-набор интеграции runtime/MCP | 366 passed, 26,07 с | Общий реальный domain/JobStore с искусственными CAD/FS; replacement IDs, replay без второго Copy, request conflict, application hold после unknown, существующий destination до записи, строгие timeout/route проверки до worker/journal. Actual stdio discovery/schema/встроенный guide также проверены. Native и новый wheel не запускались этим набором |
| Полный локальный source-набор перед native domain prototype | 5953 passed, 322 skipped, 110,43 с | Запуск без `--run-solidworks`; отдельный opt-in guard исключил CAD-подключения несмотря на неточный фильтр `not requires_cad`. Skipped не засчитываются как native passed. Это source-набор, не installed-wheel gate; следующий штатный фильтр — `not solidworks` |
| Дополнительные oracle components | 45 passed, 0,14 с; включены в итог255 | Полные topology roles, exact reference roundtrip, cached-only свойства, реестр аннотаций, параметры/состояния конфигурации и отказы при неполных данных; целый CAD capture не проверен |
| Отдельный native Copy probe установленного dev87 | passed, 8,61 с | Нормальный modern Copy ACK True/0/0, source неизменён, independent native shape/tree/config readback и own cleanup/baseline; это не L3 и не приёмка новых исходников |
| Windows file primitive probes 1–5 | Не приняты | Реальные ошибки directory sharing, path-reader/DELETE sharing и rename; failed/unknown evidence сохранены, старые receipt не повторяются |
| Windows file primitive probe 6 | 6/6, 0,042 с | Реальная NTFS-публикация нового файла сохраняет identity/bytes; writer заблокирован; строгие directory leases возвращены до освобождения file handle; final доступен для записи; существующий и raced destination не изменены. Только синтетические файлы, без CAD |
| Filesystem pure collaborator | 50 passed, 0,31 с; включены в итог255 | Class10/RootHANDLE, return-status отдельно от IOSB, pending/restore failure сохраняют ресурсы, запрещают повтор и CAD; эти отказы проверены искусственно |
| Изолированный Win32 rename research | 4 terminal cases | Full-path rename при строгих directory leases даёт sharing violation; RootDirectory-relative Win32 вызов в этой среде даёт invalid parameter. Отсутствие эффекта проверено |
| Изолированный NT rename research | 3 terminal cases | Строгий directory mode отказывает без эффекта; отдельная фаза публикации даёт success и exact held file proof; raced destination сохраняет оба файла. Rename каталогов запрещён, строгий режим возвращён |

Изолированные NTFS-пробы используют **синтетические bytes**, без CAD. Расширение
`.SLDPRT` не делает эти файлы моделями. Успешный эксперимент не означает приёмку
всех отказов filesystem collaborator, установленного wheel или публичного MCP.

Для handle-relative публикации исследован документированный user-mode
[NtSetInformationFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntsetinformationfile)
с [FILE_RENAME_INFORMATION](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information).
`ReplaceIfExists=False`; RootDirectory связывает relative filename с удерживаемым
каталогом. Статус не-PENDING интерпретируется по return value согласно
[IO_STATUS_BLOCK](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_io_status_block);
неизменённое поле IOSB после error return не является новым pending вызовом.

## Оставшиеся gates L3

1. I1/I2/I3 и четыре I4 dev88 подтверждены; общий detached preflight принят.
   Сохранять точный wheel, отчёты и trusted hashes. Эти доказательства не
   объявляют public MCP цепочку пройденной; инъекция моста не является COM-отказом.
2. Завершить ограниченный S1-B5-ACT для открытой writable part: явная активация
   через MCP с ревизией, журналом, постусловиями и собственной native-приёмкой.
   Ручная активация не заменяет этот шаг. Принятый L2 не менять.
3. Подготовить и принять публичный L3-P1: first-save/close/open/activate/edit/Save3,
   независимый native/disk readback, dirty сосед и полный baseline. Новый wheel
   требует связанных доказательств, старые результаты сохраняются как история.
4. Закрыть L3 только по конечному manifest всех шести условий; итоговая B5
   всей стадии и обязательный CI пакета остаются отдельными gates.

Все CAD-файлы, синтетические контрольные файлы и подробные отчёты находятся
в ignored `work/`. Коммиты накапливаются локально; эта контрольная точка
не запускает push/CI и не закрывает один из семи блоков стадии 1.
