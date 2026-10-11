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

Oracle ещё требует проверки целого capture на реальном CAD, проверки полного
набора данных шаблона и closing proof конфигурации/объектов. Компонентные pure
проверки не доказывают полноту всего native capture. Интеграция и MCP-фасад
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
2. Закончить полный passive source/clone oracle и проверить его на реальном
   поддержанном профиле, включая dirty сосед, persistent mapping, свойства,
   конфигурацию и view. Масса/габариты/update stamp сами по себе недостаточны.
3. Интегрировать домен и реализованный MCP-фасад. Подготовить конечные internal
   failure cases и публичную пользовательскую цепочку без дублирования CAD.
4. Полный pure → итоговый wheel → exact installed metadata/stdio → обязательная
   native/MCP-приёмка L3. Stale/replay, destination race, unknown/hold,
   source retirement и own cleanup входят в конечный gate.

Все CAD-файлы, синтетические контрольные файлы и подробные отчёты находятся
в ignored `work/`. Коммиты накапливаются локально; эта контрольная точка
не запускает push/CI и не закрывает один из семи блоков стадии 1.
