# Первое сохранение L3 — промежуточная контрольная точка

L3 **не принят**. Два публичных инструмента входят в установленный dev88;
metadata/stdio accepted73 tools/22 mutations, source pure5978/323 CAD deselected.
Installed L3-I1 начат и выполняется; конечные negative/public gates остаются.
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

1. Нормальный filesystem protocol и conflict подтверждены реальной NTFS-пробой6.
   Доказать оставшиеся failure/recovery gates совместно с CAD-протоколом:
   строгие directory leases во время любого CAD SaveAs/readback; только
   публикационная фаза допускает directory-write sharing при удерживаемом
   exact file/target handles. Полный path/reparse/identity proof до/после,
   возврат строгого режима до следующего CAD-шага; lost ACK/reacquire failure
   остаются unknown. Нет path-based overwrite или удаления final.
2. Source/clone oracle и41 mappings подтверждены Copy-прототипом3; совместимость
   filesystem leases, final writable document и source retirement — составным
   source CAD/NTFS-прототипом1. Положительный полный доменный протокол с UI guards
   и durable журналом теперь подтверждён source domain probe2. Остались конечные
   отказы/восстановление и установленный кандидат. Прототипы не заменяют эту приёмку.
3. Домен интегрирован в runtime и MCP-фасад исходников. Подготовить exact installed
   native domain positive, конечные internal failure cases и
   публичную пользовательскую цепочку без дублирования CAD.
4. Полный pure → итоговый wheel → exact installed metadata/stdio → обязательная
   native/MCP-приёмка L3. Stale/replay, destination race, unknown/hold,
   source retirement и own cleanup входят в конечный gate.

Все CAD-файлы, синтетические контрольные файлы и подробные отчёты находятся
в ignored `work/`. Коммиты накапливаются локально; эта контрольная точка
не запускает push/CI и не закрывает один из семи блоков стадии 1.
