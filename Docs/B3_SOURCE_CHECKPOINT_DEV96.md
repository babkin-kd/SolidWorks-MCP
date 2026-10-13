# B3: локальная source-контрольная точка

13.10.2026. Проверенный source HEAD — `fd43cc8`.
Все13 source groups B3 подготовлены; actual native B3 **не выполнен**.
Три стадии сохраняются, стадия1/B2–B5 остаются открыты.

## Фактические проверки

- Один полный pure-набор после интеграции всех source routes:
  **9952 passed,323 CAD deselected /514,75 с**.
  `pytest -q --tb=short --maxfail=3 -m 'not solidworks' -p no:cacheprovider`;
  source `PYTHONPATH=src`, private basetemp. Это не installed/native proof.
- Related результаты и границы I01…I13 — в [B3_ACCEPTANCE_MAP](B3_ACCEPTANCE_MAP.md).
  Actual domains/JobRunner/SQLite, искусственные native handles/getters.
- Offline exact installed B3 preflight dev96:13 groups/27 required tools,
  accepted, native_acceptance=false, can_start_native=false. Metadata83/27 report
  переиспользован; CAD/SDK workload не запускался.
- Installed metadata-only timings enabled/disabled/storage-unavailable приняты;
  при отказе telemetry mandatory journal schema3 доступен, jobs0/mutations0.
  Это не native mutation/restore/hold B4-N6.

## Неизменный installed кандидат

Version `2.0.0.dev96`; build Git
`f80ee6d80819140a8122fcf26104b0ce6760bff8`.
Wheel SHA256:
`9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa`.
Source digest:
`d861172b1437057a913c12ef7937a91eef7569deb7dd8ddae19d0d05a8655d59`.
Package source diff от build Git пуст: новые scripts/tests/docs не требуют
пересборки или установки wheel. Все22 frozen live fault helpers повторно
сверены по SHA, изменений нет. Working v1 не затрагивается.

## Native-факты и оставшиеся gates

Dev96 positive2 принят отдельно: leaf2/2,parent4/4,112 returned captures,
6 succeeded jobs/3 committed mutations,4136,97 с; original receipts/replay,
independent SKETCH/neighbor и own cleanup/full baseline подтверждены root audit.
Failed positive1 сохранён и не превращён в passed.

Finite fault owner остаётся live: **3/5 cases passed** — stale,foreign,no-effect.
No-effect имеет actual rolled_back/полное восстановление, первые два отказа
без checkpoint/native write. Controlled unknown/new-request blocker пока не
подтверждены; terminal audit/cleanup данного прогона не выполнены. После них —
три N5 dependent/equation runs и public B2. Whole B2 пока не принят.

B3 требует actual native producers, acknowledged setup/transition scopes,
private namespace/PID bridge, installed/internal/public13-group reports и
terminal own cleanup/full baseline. Конкретный путь —
[B3_NATIVE_DRIVER_MAP](B3_NATIVE_DRIVER_MAP.md). Source acceptance/cleanup=false
не заменяются сертификатами или historical wheel результатами.

Изменения накоплены локально. Эта точка не запускает push/CI, не прерывает live
CAD и не разрешает merge/main. CAD-файлы и полные журналы остаются в ignored work.
