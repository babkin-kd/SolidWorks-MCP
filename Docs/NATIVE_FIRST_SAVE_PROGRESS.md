# Первое сохранение L3 — промежуточная контрольная точка

L3 **не принят**. Публичный инструмент не зарегистрирован, новый wheel не собран
и не установлен. Приёмка открытия dev87 относится к своему точному артефакту;
новые исходники не наследуют её автоматически.

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
и native event envelope. Это source-прототип; clone capture, перенос ссылок,
составной файловый протокол и exact installed приёмка ещё не доказаны.
Отдельный source Copy/clone experiment принят ниже. Интеграция и MCP-фасад
начинаются после закрытия этих обязательных гарантий.

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
| Связанный source pure-набор, итог прототипа | 255 passed, 12,76 с | Мост, доменный протокол с искусственным CAD/FS, файловые receipt и NT-фаза публикации, пассивная классификация rectangle; native не запускался |
| Последующий связанный source pure-набор | 419 passed, 13,03 с | Дополнительно actual QueryInterface helper на fake COM, составные dimension/annotation anchors, native-plane PID нормализация и целый capture на искусственной модели. Это не новый wheel и не CAD-приёмка |
| Whole passive source probe 3 | Обе реальные собственные детали: два совпавших capture каждой; metadata_unchanged=true; 174,78 и 173,51 с | Полное чтение заявленного исходного профиля, шаблонных служебных данных и PID roundtrip. Только source-прототип, без SaveAs/clone/disk/readback или installed gate |
| Source oracle probe 1 и промежуточные passive probes | Отказы сохранены | Первый отказ до SaveAs из-за неполного учёта шаблона; последующие выявили различия raw PID/IFeature/IAnnotation interfaces. Финальный source capture не переписывает их в passed |
| Source oracle Copy probe 2 | failed; Copy вернул True/0/0, reader открылся с0/0, source/dirty сосед сохранены; clone equivalence не прошёл | На legacy-основании FeatureScope=True активный AutoSelect изменился True→False. Это не допустимая квалификация имени и не исключённый control; результат не принят. Три terminal own модели закрыты по полным прежним raw snapshots, CWD и non-STL baseline восстановлены отдельно; failed сохранён |
| Связанный source-набор после dimension roles/base controls | 289 passed, 11,98 с | Поддержанный namespace mapping, native owner/role связь, отказ active scope/unknown fields/foreign owner/изменения параметров, домен first save и базового построения. Без CAD/wheel |
| Source oracle Copy probe 3 | passed, 35,15 с; source/clone полный proof и41 mappings; own cleanup/baseline=true, pending=false, owned=[] | Свежие фикстуры созданы actual v2 builder; FeatureScope=False. Новый Copy True/0/0, независимый read-only native reader0/0; исходник/dirty сосед и staged bytes сохранены, reader roundtrip/CWD/cleanup проверены. Только source experiment; native_first_save_accepted=false, exact_installed_acceptance=false |
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
2. Source/clone oracle и41 mappings подтверждены отдельным Copy-прототипом3.
   Доказать их в составном протоколе с реальными filesystem leases, final writable
   document, source retirement, UI guards и durable журналом. Ни standalone Copy,
   ни предыдущий filesystem experiment не доказывают совместимость этих шагов.
3. Интегрировать домен и реализованный MCP-фасад. Подготовить конечные internal
   failure cases и публичную пользовательскую цепочку без дублирования CAD.
4. Полный pure → итоговый wheel → exact installed metadata/stdio → обязательная
   native/MCP-приёмка L3. Stale/replay, destination race, unknown/hold,
   source retirement и own cleanup входят в конечный gate.

Все CAD-файлы, синтетические контрольные файлы и подробные отчёты находятся
в ignored `work/`. Коммиты накапливаются локально; эта контрольная точка
не запускает push/CI и не закрывает один из семи блоков стадии 1.
