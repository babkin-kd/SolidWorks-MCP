# B1 принят: плоскость, отдельный эскиз и выдавливание

13.10.2026. **B1 принят в конечном scope стадии 1.** Стадия 1 остаётся открыта:
далее B2, B3, B4 и итоговый B5. Старый CI другой версии не принимает этот выпуск.

## Точный кандидат

- Version `2.0.0.dev94`; clean build Git `dc52ffcef06e443bea1781062e648c1773e5600f`.
- Source digest `003271e8b20a831bd09ea1de822617ed4227a8973fbc834ccdd41ea3a6f95b0f`.
- Wheel SHA256 `84c19da6866c80ff3898175622d7843413a41b1894b33ec315abe002c7013bf9`.
- Full pure перед wheel: **7157 passed /323 CAD deselected /193,31 с**.
- Installed metadata/stdIO: **79 tools /25 mutations**, без source `PYTHONPATH`.
  Рабочая v1 сохранена.

Позднейшие внешние B2/B3 preparations не входят задним числом в full7157
и не являются зависимостями frozen B1. Их309 related pure /10,27 с —
искусственная геометрия с реальным durable protocol, не native-приёмка.

## Фактические native результаты

| Запуск | Конечный результат | Время / наблюдения |
| --- | --- | --- |
| Positive internal | Sketch/extrusion/replay,8000 мм³, neighbor и baseline | **2673,43 с**,75/75 captures returned |
| Finite N4/N5 | Все7 случаев, включая собственный inverse обеих операций | **5810,00 с**,181/181 captures returned |
| Public MCP | Все5 условий: новая деталь через MCP, отдельные sketch/extrusion и replay | **3276,21 с**,3 independent full captures returned |

Все три own drivers и последовательный batch завершились normal exit0.
Trusted helper hashes10/14/27 и exact wheel совпали. После terminal exit
independently прочитана текущая CAD-сессия: documents0, active document absent,
CommandInProgress=False, UserControl=True, Visible=True. Процессы native drivers
отсутствуют; дополнительная очистка не нужна.

## Пять конечных требований

| Требование | Доказательство |
| --- | --- |
| N1: create→plane→sketch→extrude, BREP/размеры/объём | Public создаёт новую одноconfig part; exact plane PID/orientation, sketch40×20 и blind depth10. Полные independent empty/sketch/base snapshots совпадают с durable states; actual0,04/0,02/0,01 м и8000,000000000001 мм³ |
| N2: точная цель, сохранность соседа | Committed creation ID→same-connection preparation→unique HWND→canonical model, без title/roster adoption. Full neighbor/session и restored original baseline |
| N3: русские имена/membership | «Эскиз основания», «Основание», «Тело основания»; созданный sketch ID — explicit input extrusion. Полные ссылки/native membership |
| N4: stale/replay/unsupported refusals | Actual stale sketch/extrusion и foreign plane/sketch без dispatch, полное before/after equality. Actual public replay возвращает прежний result/operation. Типизированные unsupported inputs проверены pure; новые CAD-профили не объявлены |
| N5: scoped inverse либо honest unknown | Controlled Python failure после actual native snapshot, не COM throw. Sketch inverse32 и extrusion inverse40 returned steps, failed/rolled_back и полный возврат. Extrusion сохраняет borrowed sketch, его размеры и связи |

Actual inverse extrusion прошёл40 steps, превысив прежний global32: дефект
dev93 исправлен и проверен native. Finite caps44/46 — pure-проверенные верхние
границы, не число фактически выполненных шагов. Historical dev93 unknown после
own cleanup/reconciliation сохраняется и не переписывается новым успехом.

## Журнал, гарантии и границы

Root audit повторно связал actual SQLite с тремя public mutation rows, полными
payload/digest/verification. Всего11 durable jobs, ровно3 mutation jobs:
create/sketch/extrusion; нет повторных mutations или unfinished/unknown.
Sketch/extrusion committed имеют22/28 native steps. Creation имеет свой
document-create checkpoint/guard; её ledger не объявляется rectangle ledger.
Released guards, metadata/schema, full native view relations и local view
инкарнации подтверждены; independent UUID namespaces не стирались.

Own cleanup/supervisor release и original/restored session/application равны.
Non-STL preferences проверены в согласованной области; STL отложен. Новые
вспомогательные плоскости, произвольные профили/поверхности, многотельные записи,
refs и multi-config mutations остаются D2-задачами. Real rebuild-defect/late/
restart условия B4 эта N5-проверка не закрывает.

Private evidence: `work/native-rectangle-dev94-{positive,faults,public}-1`,
`work/native-dev94-chain-1`, `work/b1-dev94-final-audit-1.json`.
CAD/DB/full model snapshots остаются вне публичного Git.
