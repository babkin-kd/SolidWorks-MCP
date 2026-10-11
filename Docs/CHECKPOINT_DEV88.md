# Dev88 — кандидат первого сохранения, L3 ещё открыт

Контрольная точка 12.10.2026. Стадия 1 не завершена. L2 принят на прежнем
dev87; его факты не переносятся автоматически на dev88. Приёмка L3 выполняется
по [конечному набору](NATIVE_FIRST_SAVE_ACCEPTANCE.md).

## Точный установленный артефакт

- Версия: `2.0.0.dev88`, build Git `fa4ee2d3233d96b5e5818e39f93253db852c31ba`.
- Wheel: `work/wheels-dev88/solidworks_mcp-2.0.0.dev88-py3-none-any.whl`.
- Wheel SHA256: `420c89cb0acf824e72eb5a8a94019b6a9afd5a2d58d84510426c053984e7076b`.
- Source digest: `74c035faf564dadb1f1e4c25f1f2eb0046c3b3a24ccb14934f60344b2ca71641`.
- `source_dirty=false`; wheel validator accepted=true. Публичная публикация не выполнялась.
- Установлен только в проектную `.venv`; origin — её `Lib/site-packages/solidworks_mcp`.
  Рабочая установка v1 сохранена.
- Installed metadata/stdio accepted=true: 73 tools/22 mutations, output schemas
  и встроенный каталог согласованы. Source PYTHONPATH отсутствовал; CAD не вызывался.
  Отчёт: ignored `work/metadata-dev88-report-1.json`.

## Проверки и ограничение результата

Итоговый source pure: **5978 passed, 323 CAD deselected, 99,46 с**.
Связанный preflight/protocol/metadata-набор: **40 passed, 6,25 с**.
Первый full dev88 имел один packaging failure: версия registry template
оставалась dev87. Исправлено и проверено повторным full-набором; первый failed
журнал сохранён. Private logs: `work/pytest-first-save-dev88-full-1.log` и `-2.log`.

Полная предшествующая **source** domain-проба2 прошла за994,58 с:
committed, 24 native ledger rows, независимый full readback/mapping41,
dirty сосед и собственная очистка/baseline. Это не native-приёмка данного wheel;
[факты и прежний unknown](NATIVE_FIRST_SAVE_PROGRESS.md) сохранены отдельно.

**Installed L3-I1 начат**, один CAD-владелец, private state/report
`work/native-first-save-dev88-positive-1/report.json`. Проверены wheel/origin и
metadata; выполняется полное prepare-чтение. Пока результат не завершён,
`accepted=false`, `positive_case_passed=false`. Незавершённый COM не отменять,
пробу не запускать заново по тайм-ауту наблюдения. Unknown сохраняет журнал и
собственные модели до доказанного согласования состояния.

## Остаток

1. Дождаться именно запущенного L3-I1, проверить terminal журнал, независимый
   CAD/файловый результат и own cleanup/baseline; записать фактический исход.
2. Выполнить конечные L3-I2/I3/I4: existing/stale, no-overwrite race,
   классификация отказов/hold/replay и восстановление. Инъекцию моста отличать
   от actual native false/warning/throw.
3. Выполнить L3-P1 публичную same-wheel MCP-цепочку с close/open/следующим Save3.
4. Только после этих условий закрыть L3 и перейти к S1-B1…S1-B5; три стадии
   сохраняются. Новый push/CI пока не выполнялись; изменения накапливаются локально.
