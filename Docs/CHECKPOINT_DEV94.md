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
passed. Исполняемые файлы после полного набора не менялись.

Итоговый wheel собран и установлен только в dev-окружение проекта; рабочая v1
сохранена. Точная идентичность кандидата:

- Git: `dc52ffcef06e443bea1781062e648c1773e5600f`.
- Source digest: `003271e8b20a831bd09ea1de822617ed4227a8973fbc834ccdd41ea3a6f95b0f`.
- Wheel SHA256: `84c19da6866c80ff3898175622d7843413a41b1894b33ec315abe002c7013bf9`.
- Artifact gate: accepted, `work/wheel-dev94-report-1.json`.
- Installed metadata/stdIO: accepted, **79 tools /25 mutations**,
  `work/metadata-dev94-report-2.json`; без source `PYTHONPATH`.

Первая попытка metadata-only не смогла создать Windows named pipe в sandbox;
её failed-отчёт сохранён. Повторная проверка завершилась успешно; ни одна из
этих проверок не запускала CAD и не заменяет native-приёмку.

Свежая positive native-проверка установленного dev94 **прошла**, normal exit0,
**2673,43 с /75 returned captures**: separate sketch/extrusion и replay,
независимые8000 мм³, dirty сосед и полный own cleanup/baseline. Own documents0,
native_calls_live=false, retained_process=false. Raw report —
`work/native-rectangle-dev94-positive-1/report.json`; strict positive gate
accepted (`work/native-dev94-chain-1/positive-gate.json`). Gate принимает только
эту positive-подобласть; whole/native B1=false. Internal N4/N5 уже выполняется
в fresh `work/native-rectangle-dev94-faults-1`; public ещё не запущен. Wheel и
исполняемые зависимости batch заморожены до завершения и подтверждения очистки.

13.10.2026 подготовлен и запущен приватный последовательный batch
`work/continue_rectangle_dev94_native.ps1`, status — `work/native-dev94-chain-1`.
Он удерживает OS handles exact positive launcher/worker с проверкой PID,
parent, executable/command line и creation time; ждёт normal exit обоих, затем
strict positive gate/установленную идентичность/неизменные helper hashes.
Только после этого выполняет fresh N4/N5; следующий public driver требует
успешный exit и combined strict gate. Проверки выполняются последовательно,
без отмены COM, тайм-аута с повтором, остановки процесса или внешней очистки.
Running-report gate отдельно проверен: текущий running отчёт отклонён до
следующей dispatch. Синтаксис private PowerShell/Python проверен.

Любой отказ прекращает переходы; unknown-retained driver продолжает владеть
своими документами, batch его не убивает. Маркер `stop-after-current` внутри
batch state останавливает дальнейшие фазы между terminal-проверками, если
пользователь снова запросит паузу. Итог batch всегда требует отдельного root
аудита всех native доказательств; он самостоятельно не закрывает B1/стадию1.
Оба exact positive процесса завершились normal exit0; gate подтвердил данные
того же wheel/10 helpers. Batch автоматически перешёл к конечному N4/N5 после
full cleanup/baseline. Последующие unknown/failure остаются stop-условиями.

Последняя CAD-сессия независимо восстановлена после own cleanup. Исторический
dev93 unknown сохранён, hold reconciled; новый native driver использует новый
state/requests. Обязательные positive/internal faults/public должны относиться
к exact installed dev94; старые accepted отчёты не подставляются вместо них.

Подготовленные внешние B3/B4 helpers остаются отдельным остатком приёмки:
[B3](B3_ACCEPTANCE_MAP.md), [B4](B4_ACCEPTANCE_MAP.md). B1–B5 открыты;
imports/export/STL отложены, stage2 не расширяется. Push/новый CI не выполнялись.

Пока CAD занят, отдельно подготовлены новые внешние B2/B3 файлы (не зависимости
этого native batch): строгий PID/suppression receipt gate, finite B3-I02 public
geometry handler и независимый analytic support oracle B3-I08. Их интеграция
с существующими reader/journal/manifest — **200 related pure passed /7,79 с**.
Геометрия в новых тестах искусственная; это не native B2/B3. Эти новые files
не входили в frozen full7157 кандидата dev94; итоговый полный набор следующего
кандидата должен включить их. Production и установленный wheel не менялись.

Добавлен отдельный read-only B2 phase producer с retained canonical identities,
actual raw PID resolver, coherent session/native event watches и full neighbor
oracle. Свой30 pure /0,89 с; последующая общая related integration —
**230 passed /8,89 с** (перекрывает предыдущий200). Ни один из этих запусков
не обращался к SolidWorks. Новые файлы не являются зависимостями frozen B1.
