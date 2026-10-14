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
+
+Для public ACT подготовлен `verify_native_part_activation_public.py`: настоящий
+stdio, explicit prepare/activate/replay/no-op, durable job_get и independent
+native readback после supervisor quiescence. До CAD требуется complete four-report
+same-wheel preflight. Пассивный supervisor распознаёт строго проверенный ACT
+guard/ledger; invalid/unknown по-прежнему запрещают native fixture cleanup.
+165 связанных artificial supervisor/guard/drain cases passed (3,49 с):
+`work/pytest-activation-supervisor-1.log`.
+
+Real installed CLI preflight с заведомо неверным набором отчётов отказал до
+native connection/fixture creation: `work/native-part-activation-public-preflight-denied-1/`.
+Это metadata/admission evidence, не публичная CAD-приёмка. Already-active native
+продолжает full post-release capture; stale/fault и public native не запускались.
+Сам wheel и файлы executing case driver/helper inventory не изменены.
+
+
+**Installed ACT-N2 already_active прошёл**,1018,36 с, terminal/exit0:
+`work/native-part-activation-dev89-noop-1/report.json`.
+No-op не вызвал native activation; replay без нового эффекта. Independent full
+readback, own cleanup, full baseline/CWD/application и non-STL preferences
+подтверждены. Detached committed/no-op predicate и current trusted helpers
+проверены отдельно на том же exact wheel.
+SHA256: `8a4c3e9ab4651b39876e913379c6520e713aea557693b08e6278e1cb4005db86`.
+Whole accepted=false: N1/N2 завершены, N3 stale/foreign выполняется в
+`work/native-part-activation-dev89-stale-1/`; N4 и public ещё не запускались.
+
+
+Пока native ACT-N3 выполняется, подготовлен L3-P1 public roundtrip/edit/Save3
+driver с explicit ACT после L2 open и независимым read-only disk reopen.
+131 связанных supervisor/internal preflight tests passed (8,79 с),55 public
+contract/selection/admission tests passed (7,01 с). Это artificial contract
+evidence, не CAD-приёмка. Native L3-P1 требует first-save внутренние отчёты
+самого dev89; dev88 остаётся историческим артефактом. Wheel не пересобирался,
+native helpers текущего ACT-N3 не менялись. Новый push/CI не выполнялся.
+
+
+**Installed ACT-N3 stale/foreign прошёл**,675,30 с, terminal/exit0:
+`work/native-part-activation-dev89-stale-1/report.json`.
+Реальное own переименование после prepare сохранило отдельные original/new
+snapshots; stale_revision до mutation checkpoint/activation. Foreign document
+и configuration — document_not_open/configuration_not_found до записи.
+Independent readback, owned cleanup и full baseline/application подтверждены;
+exact wheel/current helper hashes проверены отдельно. Report SHA256:
+`32ae54c5806d68af90d7e0af3581da75da2cab2e17106f1ada1e0f50dd1e60a6`.
+Whole accepted=false; ACT-N4 controlled_after_call запущен в
+`work/native-part-activation-dev89-controlled-1/`; public остаётся.
+
+
+Отдельно проверены late/replay transport envelopes публичных native-tools:
+activate/first-save/open/Save3 ожидают job_get, без повторного CAD dispatch;
+terminal replay сохраняет тот же envelope, unknown остаётся unknown.
+18 связанных artificial transport/supervisor tests passed (3,49 с):
+`work/pytest-public-native-late-1.log`. Это не новая CAD-приёмка.
+ACT-N4 controlled_after_call продолжает полный prepare в том же процессе;
+wheel и executing case helpers неизменны, исход не повторялся.
+
+
+**Installed ACT-N4 controlled_after_call прошёл**,696,41 с, terminal/exit0:
+`work/native-part-activation-dev89-controlled-1/report.json`. Normal actual
+native receipt сохранён до bridge injection; actual_com_failure_injected=false.
+Unknown/unresolved, replay без второго activation, application hold нового
+request, independent full readback и released guards подтверждены. Exact-owned
+cleanup/empty baseline/application предшествуют accept-current-state
+reconciliation; исторический job status остаётся unknown.
+SHA256: `bff055f1c95fcc8419b7cda37f941088e2354ee7aacec7d43c7f1f43e81d0432`.
+
+Все четыре terminal internal отчёта dev89 прошли actual detached preflight:
+`work/native-part-activation-dev89-internal-preflight-1.json`. Exact wheel,
+current trusted helper hashes, finite labels и cleanup/baseline подтверждены.
+Это не public acceptance. Публичная MCP/native-проба запущена в
+`work/native-part-activation-dev89-public-1/`; whole ACT остаётся открытым.
+
+
+**Public ACT dev89 принят**,2049,55 с, terminal/exit0; accepted=true.
+`work/native-part-activation-dev89-public-1/report.json`, SHA256:
+`a0b330562c221d41daaa5524405b4fe3d9d4ed6817a547537df4441bfa6b0f7b`.
+Real stdio activate/replay/no-op, оба strict committed predicates, independent
+native readback и supervisor/owned cleanup/full baseline/CWD/application
+подтверждены. Exact wheel/current helpers checked. Five finite ACT gates закрыты
+в проверенном part scope; whole saved-file L3-P1/B5 остаётся впереди.
+