# B2: проверка подавления собственного элемента — 13.10.2026

**Совместимость API cycle подтверждена; B2 остаётся открытым.** Использован
точный установленный dev94 из [приёмки B1](B1_DEV94_ACCEPTANCE.md), без нового
wheel и без исходников в `PYTHONPATH`. Это собственный test-owner эксперимент,
а не приёмка публичных инструментов suppression/delete.

| Проверка | Фактический результат |
| --- | --- |
| Первый probe,145,33 с | Отказ до setter: actual part mode содержит `drawing_state: null`. Исправлены fixture и gate; исходный отказ сохранён |
| Второй probe,131,26 с | Suppress normally returned True. Generic resolver отверг исходный feature PID со state2; rebuild/unsuppress не вызывались. Независимое чтение подтвердило raw non-null exact canonical feature и unique original PID membership |
| Третий probe,327,85 с | Четыре setter/rebuild normally returned True. Full before/restored diff: только имя тела, сброшенное SolidWorks с «Тело основания» на «Основание» |
| Четвёртый probe,460,60 с | Выполнены цикл и однократная адресная коррекция имени тела. Повторный full native snapshot точно равен исходному. Исторический driver отказал по transient `stl_deviation` в фазе без тела; после возврата исходное значение вернулось |
| Отдельный root audit | Raw receipt повторно проверен в ранее согласованном `application_preferences_except_stl_v1`. Все остальные настройки, сосед, UI/session и полный итоговый target совпадают. Original driver report остаётся failed/probe_passed=False |
| Очистка | После каждого normally returned Python отказа root независимо проверил quiescence, original creation/HWND/PID bindings и освобождённые guards; завершён только известный idle test worker. Собственные детали закрыты без сохранения. Пустая исходная сессия/application и non-STL preferences подтверждены |

Четвёртый cycle принят как **отдельное доказательство совместимости под
согласованным non-STL scope**, с отдельными audit/cleanup hashes. Приёмка
installed инструментов B2, restart, удаления и произвольной геометрии этим
не заявляется. Причина динамического STL значения не выводится из одного diff;
STL остаётся отложенным, raw значения сохраняются в частных отчётах.

Raw state2 допустим только для собственного удерживаемого feature:
непустой original PID, raw native object с тем же canonical IUnknown,
единственная текущая membership и actual `IsSuppressed2=True`. Null, combined
или deleted states, имя и GetID как замена адресации запрещены. Generic
production PID resolver сохраняет прежние строгие правила.

В исходниках готовы internal retained-feature bridge и реестр владения,
подключённый к creation. Последующее admission требует реального succeeded/
committed creation job и retained model/configuration/feature identities.
Поздний отказ регистрации после domain commit удерживается как unknown,
без inverse/retry. Budget: один sketch + extrusion, максимум32 owned documents;
closed/replaced document bindings освобождаются только после complete roster.

Связанный итоговый pure набор: **388 passed /12,51 с**. Это source/artificial
проверки, не установленный новый wheel. Дополнительные связанные существующие
rectangle façade/journal/budget/contract regressions: **64 passed /6,00 с**.
Далее: полноценные domain/MCP
suppression и own-leaf preview/delete, final wheel и обязательная native/MCP
приёмка всех шести условий [B2](STAGE_1_BLOCK_ACCEPTANCE.md#s1-b2--размер-имя-подавление-и-удаление).
