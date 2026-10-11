# Dev89 — явная активация детали, native gates открыты

Подготовлен ограниченный S1-B5-ACT: домен, runtime и два публичных фасада
`document_prepare_activate_part_native` / `document_activate_part_native`.
Область — `native_rectangular_part_activation_v1`:
[контракт и пять конечных условий](NATIVE_PART_ACTIVATION.md).
Принятый L2 не изменён; широкая активация остаётся D2-DOCUMENTS.

## Проверки исходников

- Связанные domain/runtime/real MCP source discovery: **49 passed, 6,60 с**,
  `work/pytest-activation-source-7.log`. CAD искусственный; это не native-приёмка.
- Итоговый полный pure: **6075 passed /323 CAD deselected, 104,01 с**,
  `work/pytest-activation-full-2.log`. Исключённые CAD-тесты не passed.
- Первый общий прогон:6074 passed/1 failed,104,15 с, сохранён отдельно.
  Причина — устаревшая metadata-фикстура scopes/count; исправлена до итогового
  прогона. Предыдущие отладочные failures тестовой обвязки также сохранены.

Доказаны полный before-state, STA runtime, explicit IDs, stale отказ после
изменения geometry/dirty/view/file/active, replay/conflict, already-active no-op,
known no-effect normal error и unknown/holds при lost ACK, geometry/file/CWD/UI
delta, storage и guard-release сбое. Native и guard release однократны.
Неопределённость сохраняет exact receipts и application hold даже для новой эпохи.

Выявленный при проверке дефект порядка исправлен: guard release и полный
post-release снимок происходят до финального verdict. После committed нельзя
дописывать native ledger; этот запрет сохранён без изменения общего JobStore.
Общий контур mutations, guard и bounded open не изменён.

## Остаток

Новый каталог исходников:75 инструментов/23 операции записи. Сборка/установка,
installed metadata и фактическая native/MCP-приёмка пока не подтверждены.
`scripts/verify_native_part_activation_positive.py` готовит отдельную installed
положительную пробу ACT-N1, replay-часть ACT-N2 и собственную очистку ACT-N5.
Её отчёт сохраняет **accepted=false**: не закрывает весь S1-B5-ACT.
ACT-N2 already-active, ACT-N3 stale/foreign, ACT-N4 controlled failure и
публичная native-цепочка остаются отдельными конечными условиями.

Dev88 first-save доказательства сохранены как история точного dev88. Изменение
metadata verifier для нового каталога меняет его hash; старый отчёт не является
gate нового wheel. L3-P1, S1-B5-ACT и стадия 1 открыты. Новый push/CI не выполнялся;
изменения накапливаются локально, рабочая установка v1 сохранена.
