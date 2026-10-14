# MCP protocol bridge B4 — source SDK, 14.10.2026

Новый конечный bridge соединяет actual typed MCP messages с исходным
DimensionAdmission и переданными владельцем write/flush. Он не создаёт SDK,
процесс или COM-сессию, не закрывает pipe, не повторяет запрос и не разрешает
stop/restart/cleanup. Initialize reply и полный uncursored catalog проверяются
актуальными SDK-моделями. Planned tools должны присутствовать с outputSchema;
metadata/CAD RPC IDs уникальны, target job ID получается только из исходного
проверенного ответа. Unknown write/flush и изменённые callbacks закрывают допуск.

Итоговая связанная source-регрессия **268 passed /15,51 с**. Новый bridge-набор
71/1,51 с проверяет protocol/transport refusals, actual JobStore DTO/payload,
finite polls, no-resend и два реальных ClientSession memory сценария:

- Обычный SDK вызов на artificial Runtime/CAD: один setter, actual terminal
  committed job и bound poll. Первый response уже succeeded; позднее завершение
  этим случаем не доказывается. SDK params=None у initialized/list корректно
  исключены из переданных bytes.
- Original controller/host/Runtime/PythonWorker/SQLite: atomic arm → SDK
  timeout0 mutation с реально queued/running first reply → original durable
  callback/held finish → bound job_get running/prepared → atomic release →
  terminal succeeded/committed и второй bound poll → source replay без второго
  setter/row → atomic prepare_normal_shutdown → normal host/Runtime/controller
  close. Original refs/receipts и factories сохранены; setter один.

SDK/server и сообщения настоящие, physical byte writer/flush и CAD искусственные;
это source-проверка, не installed stdio/native-приёмка. Штатный late-result
сценарий B4-N3, independent native Q/postconditions и process recovery открыты.
Все native/stop/restart/cleanup flags false/not_run. Подключение этого bridge
к actual owned native child ещё не реализовано; текущий metadata-only launcher
CAD requests по-прежнему не допускает.

B2 native owner, frozen helpers, exact installed dev97/49b wheel и v1 не менялись.
Это второй связанный локальный source-блок после опубликованного0ea40eb;
successful CI0ea40eb его не покрывает. Полный pure после отдельной правки не
повторялся; нового wheel/push/CI нет. [Карта оставшихся gates](B4_NATIVE_DRIVER_MAP.md).
