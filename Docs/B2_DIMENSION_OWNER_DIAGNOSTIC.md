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
