# Локальная контрольная точка dev92: exact dimension ownership B1

Dev91 extrusion unknown сохранён и reconciled по независимо подтверждённой
пустой исходной сессии. Root не закрывал отсутствующие fixtures и не приписывает
это accepted cleanup неудачного driver. [Факты dev91](CHECKPOINT_DEV91.md#результат-после-возобновления).
Цель возобновлена; L2 не расширен, B1 и стадия1 остаются открытыми.

## Точный установленный кандидат

- Версия: `2.0.0.dev92`.
- Git: `dcc71c7c63ea455324db0219432d29d268b888e3`, clean build.
- Source digest: `69444b88b6b0b9faf6e38283b34bb41b45636f6a4bdaea0d06bc9861b7db1b2a`.
- Wheel SHA256: `63daff9776f915a4d480940283d67dacbc06e42683e6ec3eff0a61e23f613fa1`.
- Full source pure: **6686 passed /323 CAD deselected,153,31 с**.
- Offline wheel gate и installed metadata/stdio: **79 tools /25 mutations**,
  exact schema/provenance приняты, без source `PYTHONPATH`; CAD tools не вызывались.

Установлен только в dev .venv; рабочая v1 сохранена. Private evidence:
`work/pytest-dev92-full-1.log`, `work/wheel-dev92-report-1.json`,
`work/metadata-dev92-report-1.json`. Реальные модели и journals остаются вне Git.

## Исправление и проверки

Native interop dev91 подтвердил, что singleton extrusion display chain содержит
depth и absorbed width/height. Новый reader использует complete feature tree и
доказывает владельца каждого размера, затем выбирает только exact owned feature.
Borrowed dimensions допускаются лишь со старыми baseline annotation views;
неподтверждённый owner/view запрещает запись/retirement. Related73 pure/0,27 с.

Отдельный агент изменил только public supervisor и sibling loader: strict
rectangle committed/rolled_back gates без generic fallback, guards/ledger/full
geometry/restoration proof. Related267/14,63 с, neighbor56/6,94 с на artificial CAD
и real JobStore. Root проверил diff и интегрировал; единственный native владелец
сохранился. Полный6686 включает эту интеграцию; наборы не суммируются.

## Короткий native bridge interop

На установленном dev92 одна own fixture прошла отдельные sketch → extrusion →
owned extrusion inverse → owned sketch inverse;46 pending/returned rows, terminal/
exit0, own_count0, original baseline/application/non-STL restored. Borrowed sketch
и его views сохранились после extrusion inverse; исходный единственный view
восстановлен после sketch inverse.

Report SHA256: `9ad20f6b5c6d2d4622faa7063903a7a31a33bf1c9cad1939f0e78c61d896a6fb`.
Это interop механики native-мостов, **не полная B1 domain/MCP приёмка**: без
реального durable request/checkpoint, independent whole-session effect admission
и публичного фасада. `native_b1_accepted=false` сохранён.

## Оставшиеся gates и текущий прогон

Новый exact installed positive driver запущен:
`work/native-rectangle-dev92-positive-1/report.json`. Новый state/request, старый
unknown не повторяется. Один CAD-владелец; текущий wheel/helpers фиксированы
до terminal/quiescence. Running не засчитывается как accepted.

После принятого positive нужны finite N4/N5 driver и public MCP на этом wheel;
затем B2 → B3 → B4 → B5. Imports/export/STL остаются отложенными D-задачами.
Локальные коммиты накоплены; нового push/CI нет.
