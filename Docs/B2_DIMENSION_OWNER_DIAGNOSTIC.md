# N5 dev96: возвращённый отказ dimension owner

14.10.2026, fresh child-plane-4. Эскиз и выдавливание succeeded/committed;
original BASE-preparation succeeded. Шесть setup native pairs вернулись,
plane PID/IsSame binding подтверждён. Первый полный session read нормально
вернул ExecutionFailure с code persistent_reference_mismatch и сообщением
`Dimension no longer belongs to the persistent owner feature.`

Setup остался unknown/unresolved с mutation_confirmation_missing и без
matching verification. Actual SQLite содержит6 jobs, active jobs отсутствуют;
original creation history сохранена. Preview/delete не вызывались. Этот отчёт
не принят и не повторяется под прежним request_id.

Offline audit подтвердил84 normally returned captures,6 paired setup calls,
32 unchanged helper hashes и отсутствие pending native step/journal loss.
Освобождён только точный idle original Python owner. Independent inspection
подтвердила два equal current captures, original feature PID/window membership,
сохранную геометрию, две own модели и одну новую плоскость. Затем две собственные
детали закрыты без сохранения; empty baseline/CIPFalse/non-STL восстановлены,
historical SQL/unknown неизменны.

Private inspection SHA256:
`8cd66548679713601109c0b72f9de0d0aa0dc27c4cced8b50ccc999089ad5ad4`.
Own cleanup SHA256:
`f2e1ed29d5515fd8630cb69d04d627912f028e2832c069770cfca5b4d5ce7ed0`.
CAD-файлы, пути, журнал и полные receipts остаются вне Git.

## Короткие фактические проверки

| Probe | Что действительно проверено | Результат и граница |
| --- | --- | --- |
| 1 | Простое выдавливание + offset plane, current dimension owner/QI/PID/IsSame до InsertRefPlane, после insert/rebuild/rename | Normal resolution в4 фазах,6,49 с, own cleanup/baseline. В эскизе нет управляющих ширины/высоты; N5 не воспроизводит |
| 3 | Fully-defined B1 rectangle с Ширина/Высота и depth;3 original anchors удерживаются до plane insert, проверяются вместе с новым offset dimension | Все current и retained anchors разрешились в4 фазах,6,71 с, own cleanup/baseline. Mismatch не воспроизведён |
| 4 | Тот же fully-defined profile, но read-only captures выполняются с CIPFalse как в N5 | Все current и retained anchors разрешились,50,97 с, own cleanup/baseline. CIP сам по себе не доказан причиной |

Probe2 остановился на Python TypeError из-за пропущенного plane_object_id,
до построения геометрии. Все5 предшествующих native steps вернулись; собственный
пустой эскиз и документ очищены отдельной maintenance с полным baseline.
Первая maintenance inspection остановилась на отсутствующем Python accessor
до любых write steps; исходный отказ сохранён, новая квитанция использовала
правильный GetSketchSegments. Эти отказы не считаются успешными probe.

Следующий шаг — определить конкретный dimension/anchor и stage исходного
N5 failure, сохранив producer error без новых getters после отказа. Нет
доказательства, позволяющего ослабить owner/CAN/PID checks или объявить
исправление. N5, public B2 и общий gate остаются открытыми.

Source collector и wrapper теперь сохраняют dimension_read_failure: роль
width/height/depth/plane_offset, boundary и конкретный этап read, уже известные
original/current anchors, тип/code/message исходного исключения. Поле отделено
от admission и permission proofs; acceptance/cleanup flags false. Если current
anchor ещё не читался, сохраняется None; дополнительного getter после отказа
нет. Диагностическая ошибка не заменяет producer exception.

Root target/native-wrapper/session integration: **148 pure passed /38,73 с**,
normal exit0, внешний basetemp, без CAD. Реальный искусственный JobRunner/SQLite
сохранил setup unknown/unresolved и original producer error; refusal batch и
cleanup не вызваны. Это диагностическая подготовка, не исправление native mismatch.

## Фактический child-plane-5 — 14.10.2026

На exact installed dev96 setup снова завершился failed до preview/delete.
Новая диагностика локализовала исходный `persistent_reference_mismatch`:
`dimension_role=plane_offset`, `boundary=current_capture`,
`stage=current_anchor`; original/current anchors ещё отсутствуют (`None`).
Таким образом, отказ возникает при создании первичной ссылки на размер
смещения новой плоскости. Это не доказательство неисправности трёх исходных
управляющих размеров или достаточное основание ослаблять owner/CAN/PID.

Все 84 captures и шесть пар native setup вернулись. Фактический SQLite
содержит шесть terminal jobs: пять succeeded, setup unknown/unresolved.
Preview/delete не отправлялись; неизвестное задание не повторялось.
Offline audit подтвердил неизменность 32 helper hashes. Завершён только
точный исходный idle Python owner после доказательства отсутствия live calls.
Последующий независимый read-only осмотр завершился: два equal captures,
точные собственные PID/windows, закрытые event watches без событий,
сохранность исходных jobs и unknown. Собственная cleanup завершилась normal:
две контрольные детали закрыты без сохранения, empty baseline/CIPFalse и
non-STL preferences восстановлены, historical SQL и unknown неизменны.

Подготовлен короткий probe с двумя собственными fully-defined деталями.
Он сохраняет нормально полученные owner/QI/PID/CAN/IsSame факты до создания
anchor, чтобы при отказе не делать дополнительных CAD-getters. Probe пока
не заменяет приёмку N5 или публичной MCP-цепочки.

Probe6 остановился до плоскости на Python assertion: вспомогательный скрипт
ожидал единственный размер в feature display traversal, который включает
размеры поглощённого эскиза. Все12 предшествующих native steps вернулись;
точный idle Python owner завершён, собственная единственная деталь проверена
двумя equal captures и закрыта без сохранения. Baseline/CIPFalse/non-STL
восстановлены. Это ошибка probe, не результат N5. Fresh probe7 выбирает depth
по canonical owner из полного census; исходный failed отчёт не изменён.

Probe7 завершился normal за67,54 с: две fully-defined детали, точная активация
основной детали, четыре фазы before/insert/rebuild/rename,15 current anchors
и retained anchors разрешились.55 native steps вернулись, owner CAN/PID/IsSame
не дали mismatch. Сосед сохранился; обе собственные детали закрыты без
сохранения, baseline/CIPFalse/non-STL восстановлены. N5 mismatch снова не
воспроизведён; успешный probe не принимает N5. Длительный прогон не повторён.

Private child-plane-5 independent inspection SHA256:
`3cbeb588d6966de903568c84eda4bbff6977abfd2887e0b4ae572c5aa1917868`;
own cleanup SHA256:
`529ca5d9d0594f4b494af308fe52c7f4b47496379d2927e193231bdce7691262`.
