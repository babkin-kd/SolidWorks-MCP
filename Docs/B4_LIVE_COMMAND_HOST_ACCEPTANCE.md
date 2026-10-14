# Конечный командный host B4 — 14.10.2026

Host обслуживает исходный конечный command receiver в собственном Python
потоке. Бюджет, allowlist, module/class/methods, nonce/root и original owner
проверяются; новых COM getters, CAD dispatch или process-stop полномочий нет.
Команда публикуется целиком через exclusive partial+flush/fsync+rename без
перезаписи. Потеря публикации/ack не вызывает повторного действия.
`stop_waiting` заканчивает только ожидание файла; entered action должен
вернуться. Конец потока наблюдается по исходному Thread/join/is_alive,
а не по timeout или промежуточному phase.

Итоговая связанная source-проверка: **265 passed /15,13 с**. Host-набор51/5,70 с
включает artificial-CAD цепочку: atomic arm → original Runtime/PythonWorker/
guard/SQLite mutation → durable callback/held finish → atomic release →
terminal succeeded/committed → replay без второй записи → atomic
prepare_normal_shutdown → normal host/Runtime/controller completion.
Setter один, исходные объекты/receipts сохранены, factories восстановлены.
Это реальные Python/SQLite механизмы с искусственным CAD, не native Q.

Actual installed metadata attempt11 exact dev97 прошёл: SDK83, normal child
exit0, journal=[], metadata/control/inspection/live-host gates true. Единственная
inspect-команда обработана при открытом исходном Runtime; original host thread
return наблюдён перед normal controller completion. Actual manifest11 helpers
сверен после прогона. CAD/job calls=[], native Q/recovery/restart/reconciliation
not_run. Профиль `dimension_commands_live` разрешает только inspect budget1.

Installed wheel не менялся: dev97, build
49b899c9c6048c89be81e20c9c5c29f0e4ee50d4, SHA
702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b;
source PYTHONPATH исключён. Attempt10 подтвердил normal path прежнего helper
manifest. Exception-path test затем выявил неверное имя переменной:
263passed/1failed; исправлен код wrapper, далее265 passed и fresh actual11.
Исходное main exception сохраняется и при ошибке наблюдения wait; нормальное
завершение при таком отказе не заявляется.

Actual native arm/dispatch, независимые postconditions/admission Q,
stop/restart/reconciliation открыты в [карте](B4_NATIVE_DRIVER_MAP.md).
B2 native owner и его frozen helpers не менялись. Это локальный блок после
опубликованного0ea40eb; successful CI0ea40eb его не проверяет.
Полный pure после отдельного helper-блока не повторялся; нового push/CI нет.
Частные отчёты в ignored work/, рабочая v1 сохранена.
