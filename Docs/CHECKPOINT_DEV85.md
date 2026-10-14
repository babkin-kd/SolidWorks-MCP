# Локальная контрольная точка dev85: clean native CloseDoc

Один законченный lifecycle-блок после пакетной отправки dev82. Clean close
принят: internal12/12 (68,40с), public MCP10/10 (64,92с), installed metadata69/20
на одном wheel. Полный pure перед wheel4673/323 CAD deselected (60,00с);
после external verifier defaults fix итоговый пакет4677 passed/323 deselected
(60,07с). Все5 своих моделей закрыты в каждом final прогоне, empty/free baseline
и non-STL preferences восстановлены; final журналы не содержат unknown/holds.

## Точный кандидат

| Поле | Значение |
| --- | --- |
| Wheel Git | `16c2d069ab2c71f8933a4435aa59c7623f3ff511` |
| Версия | `2.0.0.dev85` |
| Source digest | `db138e3e06b37476b8ba03205337dbae6d204850cf1aeb04ebfa2e33defc364a` |
| Wheel SHA256 | `68e50266a8df62a1ea38e2ba010bc852aa068259d809075998cb3e0725d3ed28` |
| Scope | `native_document_close_clean_v1` |
| Передача в public | Same wheel/version/Git/digest и final verifier/fixture/helper hashes |

Финальные standalone verifier/defaults и публичная документация фиксируются
последующим локальным коммитом; исполняемый installed package не менялся.
Обновление внешних verifier/test/docs не требует нового wheel или переноса
приёмки на изменённый пакет. Чистый build provenance остаётся привязан к16c2d06.
Полные hashes/report evidence и ограничения — в
[NATIVE_DOCUMENT_CLOSE_ACCEPTANCE](NATIVE_DOCUMENT_CLOSE_ACCEPTANCE.md).

## Реальное покрытие и исправления

4 успешных CloseDoc в каждом final прогоне закрыли5 моделей: assembly+explicit
hidden collateral, drawing и две parts. Survivor guard counts3/2/1/0; dirty
сосед, все baseline files, metadata/views/selection/physical geometry,
application settings и request replay/stale/invalid retired IDs проверены.
Incoming reference от surviving assembly отказал на реальном компоненте.

Native выявил два дефекта: пустой modern dependency getter на SW2023 и
неподтверждённую активацию UI-locked survivor. Введены independent dependency
census и phased verified UI release с удержанием CIP/selection. Предыдущий
dev84 unknown сохранён и согласован для own-fixture cleanup без retry.
Public1 остановился до любых MCP writes из-за отсутствующих defaults в ToolSpec;
7 read jobs terminal proof разрешил завершение только exact test PID и cleanup.
Final internal2/public2 приняты на исправленном одинаковом verifier hash.

## GitHub и пакетная отправка

По указанию пользователя актуальный main3ab795e получен через Git и объединён
со stage-1-fixes. README сохранил актуальное описание форка. Один пакетный push
`d57e524c6abd4e7f97d8405b90486bc76feb5fe4` устранил dirty в
[PR15](https://github.com/babkin-kd/SolidWorks-MCP/pull/15).

[CI run38146512142](https://github.com/babkin-kd/SolidWorks-MCP/actions/runs/38146512142)
реально запустился:4523 passed/1 failed/323 CAD deselected (152,38с).
Frozen lockfile прошёл; unit-and-build остановился до build/installed metadata.
SQLite-тест не создавал ignored work/ на чистом runner. Локальный88e479a
исправляет setup и добавляет fresh-checkout regression;116 связанных pure
прошли, затем исправление вошло в успешный полный final пакет4677.

Повторного push после отдельной CI/MD правки нет. Local clean-close и CI-fix
накапливаются до следующего согласованного цельного пакета. У remote CI остаётся
failure; успешная local/native-приёмка его не заменяет. Draft PR/main сохраняются.

## Остатки стадии1

S1-15 частично закрыт: current-file Save3 и clean close имеют свои точные
приёмки. First save/open, clean unsaved native, dirty-owned/retained-reference
close и общий N6 остаются. Далее L2 explicit native open, затем L3 first save;
расширение стадии2 отложено до конечной [матрицы](STAGE_1_REQUIREMENTS_MATRIX.md).
20 из22 требований открыты полностью/частично; общий N0–N6 не завершён.
Background/throw/no-effect/release fault пока pure-only;5 моделей не доказывают
масштаб1000+. Старые native результаты не переносим автоматически на dev85.
Legacy pilot20/20 отдельно,303 legacy cases не запускались; повтор не нужен
для неизменённого legacy контура. Import/export/STL остаются отложенными.
