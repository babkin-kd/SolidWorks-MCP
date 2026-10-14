# Ограниченная проверка inspect-команды — 14.10.2026

Вспомогательная оболочка получила конечный командный приёмник, привязанный
к исходному controller, nonce, PID, state и exact wheel. Metadata-профиль
разрешает только одну `inspect`-команду; arm/release/shutdown исключены его
неизменяемым allowlist. Чужая последовательность, повтор, потеря записи или
подтверждения закрывают приёмник без автоматического повторения.

Связанные source-тесты: **196 passed /9,19 с**, отдельно от CAD. Первая попытка
тестов не прошла из-за ACL временного каталога и не засчитана. После разрешённого
запуска проверены команды, controller и parent gates; полный pure не повторялся.

Actual installed attempt9 прошёл: SDK83 tools, metadata/control/inspection gates
true, original child normal exit0, complete journal `[]`, восстановленные
factories и durable inspect acknowledgement. CAD/job calls `[]`; native Q,
recovery/restart/reconciliation остаются `not_run`. Это приёмка metadata-only
оболочки, не приёмка B4 или CAD.

Точный установленный кандидат: dev97, build
`49b899c9c6048c89be81e20c9c5c29f0e4ee50d4`, wheel SHA
`702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b`.
Пакет не пересобирался/переустанавливался, source PYTHONPATH исключён.
Рабочая native B2-проверка и её helpers не менялись.

Попытка7 отказала до создания процесса при чтении wheel из-за ACL.
Попытка8 закончилась exit1 после SDK: wrapper ошибочно ожидал next_sequence=2
у уже закрытого приёмника. По его действительному контракту значение `None`;
исправлено ожидание wrapper, ограничение бюджета не ослаблено. Эти отчёты
сохранены как failed; новая попытка9 использовала новый state.

Полные частные отчёты остаются в ignored work/. Изменения накоплены локально,
без отдельного push/CI. Действующий remote CI25df не покрывает этот блок.
