# Кандидат dev94: конечный журнал восстановления B1

Исправляется фактический отказ dev93 N5: global limit32 остановил inverse
после удаления extrusion и rebuild, перед retirement пустого annotation view.
[История и безопасная очистка](CHECKPOINT_DEV93.md).

`JobStore.record_mutation_step` выбирает конечный cap по сохранённому operation:
sketch.create_rectangle44, part.extrude_rectangle46; все другие операции32.
Caller/payload/alias его не расширяют. Schema3, transactional pending/returned,
проверка outcome, holds и no-retry сохраняются. Новых tools/scopes нет.

Related123 passed /4,86 с: полный durable inverse44/46, атомарный отказ сверх
cap, pending/mismatch, generic32, сохранность before/hold/replay. Два случая
используют реальные execution/coordinator/store и strict restoration gate,
но геометрия искусственная — это не native-приёмка.

Версии package/pyproject/uv.lock/registry template согласованы на2.0.0.dev94.
Полный pure-набор принят: **7157 passed /323 CAD deselected /193,31 с**, exit0;
private `work/pytest-dev94-full-1.log`. CAD cases не запускались и не считаются
passed. Исполняемые файлы после полного набора не менялись. Новый wheel ещё не собран
и не установлен; точные Git/source digest/SHA256 и installed/native результаты
будут добавлены по факту. Рабочая v1 и текущий установленный dev93 сохранены.

Последняя CAD-сессия независимо восстановлена после own cleanup. Исторический
dev93 unknown сохранён, hold reconciled; новый native driver использует новый
state/requests. Обязательные positive/internal faults/public должны относиться
к exact installed dev94; старые accepted отчёты не подставляются вместо них.

Подготовленные внешние B3/B4 helpers остаются отдельным остатком приёмки:
[B3](B3_ACCEPTANCE_MAP.md), [B4](B4_ACCEPTANCE_MAP.md). B1–B5 открыты;
imports/export/STL отложены, stage2 не расширяется. Push/новый CI не выполнялись.
