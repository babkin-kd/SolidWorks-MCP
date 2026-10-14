# Приёмка ограниченного первого сохранения — dev89

**L3 принят 12.10.2026 в заданном ограниченном объёме.** Семь внутренних
отчётов L3-I1…I4 и публичная цепочка L3-P1 подтверждены на одном установленном
wheel без source `PYTHONPATH`. Общая стадия 1 остаётся открытой: B1…B5.

## Привязка и конечный результат

- Wheel: `solidworks_mcp-2.0.0.dev89-py3-none-any.whl`.
- Git: `ea93a0b7d9d0b63408539d7a3f91f889eca38034`.
- Source digest: `6fbc3b236273cf83dd0c7832b6b1057682d689144d815073913d7608edcdc6f6`.
- Wheel SHA256: `e0f50523544199d064a51b13cc20bd8b131dea3ca986e1e17e6572fcdc286b8c`.
- Installed metadata: 75 инструментов /23 мутации, package origin проверен.
- Public report SHA256: `7a275acfac7a289508cadc1eb9cb4de0865a1d2fb6670853bb88df4897c7ea04`.

Публичный процесс завершился exit0, `phase=terminal`, `accepted=true`,
3183,64 с. Все четыре конечных условия пройдены:

| Условие L3-P1 | Фактическое доказательство |
| --- | --- |
| Первое сохранение и replay | Actual public job succeeded/committed, replacement ID mapping и независимое чтение; повтор без второй записи |
| Повторное открытие и редактирование | Clean close/open, explicit MCP activation, свежая ссылка на размер, 14 мм, Save3; объём 11200 мм³ |
| Независимое чтение файла | Повторное read-only открытие после закрытия; native geometry/tree/dimensions и dirty сосед сверены независимо |
| Очистка и baseline | Exact-owned cleanup после quiescence; owned=[], native_calls_live=false; original/restored roster и application совпали |

Все девять внешних captures вернулись. Журнал публичного сервера содержит
22 succeeded jobs и 10 committed mutations; running/unknown не осталось.
Точные 20 helper hashes сверены с доверенным inventory драйвера на момент приёмки.
Отдельный detached audit повторно подтвердил actual committed first-save job
и общий gate всех семи внутренних отчётов. Приватный отчёт, CAD и SQLite
остаются в ignored `work/`, в Git публикуется только эта сводка.

Позднейшие изменения metadata helper для dev90 не переписывают этот отчёт
или его hashes. Новому кандидату нужны собственные installed/native gates;
старую приёмку нельзя переименовать в приёмку нового wheel.

Поддержанные non-STL настройки совпали с исходными. STL preferences исключены
из обязательного scope; их приёмка не объявляется. Их наблюдаемое совпадение
в этом отчёте не закрывает отложенную задачу STL.

## Внутренние случаи и ограничения

L3-I1: actual first save/readback/mapping41/replay. L3-I2: existing destination
и stale до записи, Copy0. L3-I3: actual destination race, no-overwrite,
failed/rolled_back, сохранность source/neighbor/foreign file. Четыре L3-I4:
управляемые false/warning/throw/incomplete ответы **после нормального реального
Copy**, unknown/hold/no-repeat и точное reconciliation с сохранением
исторического unknown. Это не свидетельство реального COM false/warning/throw.
Точные SHA256, времена и ограничения: [ход приёмки](NATIVE_FIRST_SAVE_PROGRESS.md).

Scope остаётся прежним: own unsaved self-contained one-configuration part
с одним прямоугольным основанием, новый локальный `.SLDPRT` без перезаписи;
полностью наблюдаемый сосед того же профиля. Типы с внешними ссылками,
произвольные соседние модели и first save assembly/drawing остаются D2-DOCUMENTS.
L2 не расширен. Приёмка L3 не заменяет самостоятельные sketch/extrusion B1
или сквозной B5 итогового wheel.
