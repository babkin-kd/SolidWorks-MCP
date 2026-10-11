# Конечный набор приёмки L3

Это распределение шести условий L3 из [приёмки блоков](STAGE_1_BLOCK_ACCEPTANCE.md),
а не новые требования к стадии 1. **L3 открыт**: source-прототипы и pure-тесты
не заменяют приёмку точного установленного wheel. Статус реализации и факты:
[контрольная точка](NATIVE_FIRST_SAVE_PROGRESS.md).

## Граница и результат

Собственная несохранённая part: одна конфигурация, один solid, независимое
прямоугольное blind основание; новый локальный путь `.SLDPRT` без перезаписи.
Dirty сосед — собственная контрольная part того же полностью наблюдаемого
профиля. Неизвестные поля шаблона, иной профиль, incoming/outgoing refs и
неподдержанная файловая система отвергаются до эффекта.

Результат — проверенный native-файл и живой итоговый документ для дальнейшего
редактирования/Save3. При замене документа старые IDs явно выведены из обращения;
ссылки разрешаются заново в итоговом документе. Только Copy на диск недостаточен.
Все обязательные гарантии [общего контракта](STAGE_1_BLOCK_ACCEPTANCE.md)
сохраняются, включая полный baseline, журнал, ревизию и запрет повтора unknown.

## Распределение проверок

| Метка | Проверка и конечное доказательство | Условия L3 | Уровень |
| --- | --- | --- | --- |
| L3-I1 | Успешный first save: полный журнал Copy/read-only readback/no-replace/final open/source retirement; независимые BREP, дерево, размеры, конфигурация, file identity/bytes и mapping; released guards и terminal own cleanup | 1, 2, 5, 6 | Внутренняя native-проверка установленного wheel |
| L3-I2 | Существующий destination и stale revision: отказ до первого native write; прежние bytes/identity, модель и baseline сохранены | 3, 5 | Внутренняя проверка на реальных файлах и CAD |
| L3-I3 | Destination появляется после prepare, перед публикацией: чужой файл не заменён; actual CAD-эффект и stage учтены, известное восстановление доказано либо сохранён unknown/hold | 3, 4 | Внутренняя native-проверка с управляемой файловой гонкой |
| L3-I4 | False/warning/throw и неполный receipt: исход классифицирован по фактическому эффекту, нет второго Copy/Close; pending не очищается, terminal cleanup касается только own объектов | 4 | Доменный/adapter-набор; управляемые отказы моста после реального CAD отдельно помечены как инъекция |
| L3-P1 | Публичный prepare/first-save возвращает правильные IDs, путь и durable job; replay без новой записи; точный clean close/open, заново разрешённый размер, следующий Save3 и независимый readback; dirty сосед и исходный baseline сохранены | 2, 5, 6 | Публичная MCP/native-цепочка того же установленного wheel |

Один сценарий может подтвердить несколько условий. L3-I2 содержит два
предварительных отказа; L3-I4 — три класса ответа и неполное свидетельство.
Отдельный CAD-прогон для каждой pure-вариации не требуется. Подробные отказы
проверяются внутри, публичный прогон проверяет контракт и пользовательскую
цепочку; одинаковый физический сценарий повторяется только ради отдельного
существенного свойства. Не добавлять новые профили, типы документов или load modes.

Искусственный COM-ответ не является свидетельством реального COM-отказа.
При инъекции после настоящего вызова отдельно фиксируются исходный native
receipt, момент инъекции и независимо наблюдаемый эффект. Неполученный native
результат остаётся непроверенным; pure-покрытие нельзя записать как native passed.

## Закрытие блока

Положительный installed-прогон L3-I1 подготовлен в
`scripts/verify_native_first_save_positive.py`. Параметры: `--run-solidworks`,
новый `--state-dir` внутри ignored `work/`, `--wheel`, `--expected-version` и
`--expected-git-sha`. Запускать проектным dev-интерпретатором без source
PYTHONPATH. До CAD проверяются точный wheel, installed origin и metadata/stdio;
после — полный протокол, независимый native readback и own cleanup/baseline.
Отчёт сохраняет `positive_case_passed`, но **accepted=false**: один положительный
прогон не закрывает L3-I2…L3-I4 и L3-P1. Source-проба использует тот же core,
явно сохраняет source scope и также не объявляет installed-приёмку.

L3-I2 реализован в `scripts/verify_native_first_save_rejections.py`: prewrite
conflict и реальное переименование собственного основания после prepare с
последующим stale refusal; native Copy ожидается ровно ноль раз. Первый сбой
JSON-проекции и отдельная own cleanup сохранены в контрольной точке dev88.

L3-I3 подготовлен в `scripts/verify_native_first_save_race.py` с теми же
wheel/version/Git/state/opt-in параметрами. Продукт выполняет настоящие
Copy/readback/no-replace; контролируемый производитель создаёт чужой файл
эксклюзивно непосредственно перед publication. Отчёт требует ровно один Copy,
stage open/close и publication, known rolled-back исход, сохранённые foreign
bytes/identity, пустую own stage, replay без повторного эффекта, full models и
baseline. `scripts/verifier_first_save_race.py` проверяет detached журнал;
он не является независимым CAD/file oracle. Связанные 18 pure-тестов прошли
на искусственном CAD/FS; физическая native-приёмка L3-I3 прошла на installed dev88
за874,27 с, с known rollback, foreign preserved, replay и cleanup/baseline.

L3-I4 подготовлен в `scripts/verify_native_first_save_fault.py`. Кроме обычных
installed/opt-in параметров требуется явный `--fault`: `false_after_copy`,
`warning_after_copy`, `throw_after_copy` или `incomplete_after_copy`. Один процесс
проверяет один выбранный случай. До инъекции отдельно фиксируется настоящий
normal Copy receipt; это сбой моста, не свидетельство native COM false/warning/throw.
Требуются unknown/unresolved, replay без второго Copy, блокировка другого request,
неизменные исходные модели, released guards и отсутствующая publication.
Только после доказательства терминального реального Copy допускается test-owner
read-only reader для независимого full clone/41-role readback. Его точное закрытие,
known own CWD restore, retained stage bytes и empty baseline предшествуют internal
`accept_current_state` reconciliation. Исторический job остаётся unknown;
снимается только его exact hold. Любое неподтверждённое состояние сохраняет процесс
и ресурсы. Скрипт проверен на синтаксис/CLI; installed native L3-I4 warning_after_copy
запущен и пока не завершён. Остальные fault modes и публичная цепочка остаются видимыми задачами.

Конечный отчёт связывает все шесть условий с метками, фактическими результатами
и частными артефактами. Он фиксирует wheel SHA/build identity, установленный
package origin без source PYTHONPATH, версии SolidWorks, hashes верификаторов,
журнал и независимые CAD/файловые свидетели. Протокольный predicate
`scripts/verifier_native_first_save.py` проверяет согласованность журнала,
но не заменяет независимое чтение CAD или файла.

L3 закрывается только после связанных/full pure-проверок, installed metadata/stdio
и обязательной native/MCP-приёмки с доказанной очисткой. Failed/unknown и
пропущенные случаи сохраняют свои статусы; итоговая S1-B5 same-wheel цепочка
остаётся отдельным выпускным gate. До этого L3 и стадия 1 открыты.


## Подготовка публичного L3-P1

`scripts/verifier_first_save_public_contract.py` задаёт supervisor operation,
default и float contracts для first-save/close/open/Save3 и dimension read/edit.
Выбор глубины допустим только из полного текущего трёхразмерного inventory,
по writable owner Boss/Extrusion, mm, наблюдённому значению и подтверждённому
opaque object_id; имя/порядок не служат fallback. Связанные selector/runtime/facade
source-тесты: 30 passed (3,31 с). Это подготовленный контракт; публичный native
driver и прогон ещё не завершены, L3-P1 не принят.
