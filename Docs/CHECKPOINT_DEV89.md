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

Dev89 собран и установлен только в проектную `.venv`. Exact wheel:
- Git: `ea93a0b7d9d0b63408539d7a3f91f889eca38034`, clean build.
- Source digest: `6fbc3b236273cf83dd0c7832b6b1057682d689144d815073913d7608edcdc6f6`.
- Wheel: `work/wheels-dev89/solidworks_mcp-2.0.0.dev89-py3-none-any.whl`.
- Wheel SHA256: `e0f50523544199d064a51b13cc20bd8b131dea3ca986e1e17e6572fcdc286b8c`.
- Installed metadata/stdio accepted:75 tools/23 mutations, output schemas и
  origin/provenance без source PYTHONPATH; CAD tools не вызывались.
  Свидетельство: `work/metadata-dev89-report-1.json`.

Положительная installed native-проба **прошла за1027,38 с**:
`work/native-part-activation-dev89-positive-1/report.json`, terminal/exit0.
Точная цель активирована один раз; replay без нового эффекта. Полный независимый
native readback сохранил target/dirty сосед; 25 captures returned, exact-owned
cleanup, baseline/CWD/application context и non-STL preferences подтверждены.
Detached committed predicate и current trusted helper hashes проверены отдельно.
Report SHA256: `012f64de56d1f38aa47698e99cbd6fd085047cc170a8bbafe5d5f3c1e77bee19`.
`activation_positive_passed=true`, **accepted=false**: это ACT-N1 и replay-часть
ACT-N2, не вся задача. Следующий `already_active` case выполняется в
`work/native-part-activation-dev89-noop-1/`; новый единственный CAD-владелец.
Все package/helpers её артефакта сохраняются неизменными до терминального исхода.
Native/MCP gates остаются открыты.
`scripts/verify_native_part_activation_positive.py` готовит отдельную installed
положительную пробу ACT-N1, replay-часть ACT-N2 и собственную очистку ACT-N5.
Её отчёт сохраняет **accepted=false**: не закрывает весь S1-B5-ACT.
ACT-N2 already-active, ACT-N3 stale/foreign, ACT-N4 controlled failure и
публичная native-цепочка остаются отдельными конечными условиями.

Dev88 first-save доказательства сохранены как история точного dev88. Изменение
metadata verifier для нового каталога меняет его hash; старый отчёт не является
gate нового wheel. L3-P1, S1-B5-ACT и стадия 1 открыты. Новый push/CI не выполнялся;
изменения накапливаются локально, рабочая установка v1 сохранена.

+
+В ходе положительной native-пробы без изменения package/её helpers подготовлены
+detached activation predicate и три finite negative/no-op сценария.
+27 pure predicate cases passed (4,63 с): `work/pytest-activation-protocol-2.log`.
+Это manufactured journal/guard evidence, не native CAD. Новый driver прошёл
+синтаксис/CLI; его native cases и public gate остаются открытыми.
+
+
+Подготовлен detached preflight перед public ACT: нужны positive/already_active/
+stale/controlled_after_call terminal отчёты одного exact wheel, current trusted
+helper inventories, finite passed labels, independent readback и cleanup/baseline.
+Known failures, исторический unknown и его exact reconciliation различаются.
+49 связанных artificial admission/protocol cases passed (11,23 с):
+`work/pytest-activation-admission-1.log`. Полный actual four-report gate ещё не
+принят: already_active выполняется, stale/controlled_after_call не запускались.
+