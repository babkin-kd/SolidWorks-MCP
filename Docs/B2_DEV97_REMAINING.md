# Конечная очередь preview/delete на dev97 — 14.10.2026

Точный кандидат: `2.0.0.dev97`, build
`49b899c9c6048c89be81e20c9c5c29f0e4ee50d4`, wheel SHA256
`702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b`.
Установленный пакет проверяется без source PYTHONPATH. Результаты dev96
сохранены [отдельно](B2_DEV96_REMAINING.md) и не принимают новый wheel.

Поддерживается удаление собственного конечного выдавливания с сохранением
эскиза и соседей. Удаление произвольного графа зависимостей остаётся D2-DELETION.
Эта очередь не расширяет объём B2 и не снимает обязательные гарантии.

Пассивная подготовка выполнена без CAD: проверен SHA фактического wheel,
сохранён manifest всех 32 helpers N5. Это подготовительный снимок, не
положительный gate и не разрешение dispatch до окончания текущего владельца.
Изначальный запуск чтения wheel получил ACL-denied и не засчитан; повторное
разрешённое чтение завершилось normal exit0.

Исправлена жёсткая привязка public preflight к dev96: поддержаны явно выбранные
dev96/dev97, при этом package_version отчёта обязана совпасть с requested
version, а полные wheel/build/installed metadata/SQL/helper проверки сохранены.
121 связанных pure-тестов прошли /55,61 с. Смешивание requested dev96 с
dev97-отчётом отклонено до installed provider; неподдержанные и boolean версии
также отклоняются. Это искусственные доменные/SQLite сценарии, не actual public
приёмка dev97: positive1 уже принят ниже, faults gate ещё ожидается.

Дополнительно actual historical positive/fault отчёты dev96 с их действительными
SHA отклонены для requested dev97 до package provider/COM. Файлы отчётов
сохранили SHA, новый state не создан; CAD/provider calls=[]. Это реальная
пассивная проверка несовместимых свидетельств, не приёмка CAD нового кандидата.

| Очередь | Пользовательский результат | Конечная проверка | Статус / условие допуска |
| --- | --- | --- | --- |
| Positive | Preview и удаление собственного leaf, повтор запроса без второй записи | BASE→SKETCH, retired PID, actual SQL committed, сохранный эскиз/сосед, terminal cleanup и полный baseline | Принят positive1:2/2,6023,32 с, normal exit0, actual SQL6/3committed, own cleanup/baseline; exact пассивный gate passed |
| Faults | Объяснимые отказы stale/foreign/no-effect и безопасное поведение при потере наблюдения | Все пять конечных случаев, actual SQLite, unknown остаётся unresolved, повтор не пишет, hold блокирует новый запрос, cleanup/baseline | Fresh faults1 на dev97 запущен после terminal positive и exact report/helper gate; итог pending |
| N5 child_plane | Отказ удалить leaf с дочерней плоскостью | Setup succeeded/committed; preview/execute `leaf_deletion_unsupported`, оба replay без dispatch; полный before/after, PID, сосед, event envelope, cleanup/baseline | not_run на dev97; setup failure запрещает preview/delete; прежний owner mismatch остаётся непринятым |
| N5 unused_equation | Сохранить неподдерживаемые уравнения при отказе | `first_save_snapshot_unsupported`, четыре запроса с replay, paired native setup, неизменный журнал/состояние вне новых отказов, cleanup/baseline | not_run; отдельный свежий последовательный прогон |
| N5 linked_equation | Сохранить связь и исходный файл уравнений при отказе | Предыдущие условия плюс identity/timestamps/bytes/SHA частного файла до/после | not_run; отдельный свежий последовательный прогон |
| Public MCP | Размер 12 мм / объём 9600 мм³, русское имя, подавить/вернуть и удалить собственный leaf | Все пять finite public cases, opaque ID/native mapping, actual SQL/replay, independent full observer и baseline | not_run; exact positive/fault preflight, внутренние N5 gates выполняются первыми |
| Общий B2 | Законченный блок редактирования простой детали | Сводка всех шести условий B2, один wheel, реальные постусловия и обязательный пакетный CI | Открыт; отдельный passed сценарий не закрывает блок |

Native-владелец только один. Пока очередной native-прогон выполняется, допустимы чтение
отчётов и подготовка helpers/контрактов без COM. Следующий прогон запускается
только после terminal отчёта, проверки actual SQL, отсутствия pending calls
и подтверждённого восстановления исходной сессии. Между снимками
native_calls_live=false не означает завершения процесса.

Неизвестные старые задания не повторяются и не объявляются успешными.

Повторная пассивная проверка во время faults1: все32 helpers следующей N5
очереди и22 helpers текущего владельца сохранили SHA; ссылка на принятый
positive1 совпадает. В текущем отчёте прошли stale/foreign/no-effect (3/5),
выполняется `leaf_observation_unknown`. Это промежуточное состояние, а не
terminal gate; следующие native-запуски ещё не разрешены. CAD/process calls
пассивной проверки отсутствуют. Подготовка очереди не меняет текущий прогон.

Пассивный [чек-лист следующих запусков](B2_DEV97_DISPATCH_CHECKLIST.md)
фиксирует точные labels, команды и границы автоматических gates. CLI N5
сам проверяет только positive; faults и terminal/cleanup предыдущего владельца
проверяются отдельно. Public preflight не принимает три внутренних N5 и
публичную N5 refusal chain автоматически; эти остатки остаются видимыми.

Пассивный `scripts/verifier_b2_terminal_prerequisites.py` сводит actual
positive/fault validators без metadata subprocess и COM. До candidate identity
требует terminal reports/cleanup/baseline; сверяет exact wheel, оба parent
reports и полные raw SQLite journals до/после проверки. Gate не разрешает
dispatch/cleanup: original process exit всё равно наблюдает один владелец.
70 связанных pure-тестов прошли /44,96 с на artificial domain и реальном
SQLite, включая изменения отчётов/БД в ходе проверки. Actual незавершённый
faults1 отклонён до candidate checks: CAD/process calls=[]. Положительный
actual same-wheel gate ещё не запускался, пока текущий процесс выполняется.
Собственные контрольные документы закрываются без сохранения после окончания
вызовов и проверки владения; пользовательские документы не затрагиваются.
Все частные модели, журналы и полные отчёты остаются вне публичного Git.
