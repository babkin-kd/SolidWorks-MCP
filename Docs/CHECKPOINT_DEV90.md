# Локальная контрольная точка dev90 — отдельные стадии B1

**Dev90 собран и установлен; native B1 ещё не принят.** Четыре отдельные
prepare/create sketch и prepare/extrude функции подключены к runtime/CAD.
Настоящий metadata/stdio79/25 принят без source `PYTHONPATH`; v1 не менялась.
Нового push/CI нет, main остаётся стабильным.

## Результат и граница

Эскиз возвращается закрытым, fully-defined и без тела, с устойчивым
`sketch_object_id`. Новая подготовка выдавливания использует этот ID и новую
полную ревизию; результат возвращает `feature_object_id`. Реальный FeatureCatalog
сверяет exact PID с независимым native anchor и повторно проверяет сессию.

Scope прежний: active writable unsaved one-configuration part, существующая
origin plane, прямоугольник, одно blind основание и полностью наблюдаемый
rectangular сосед. Имена по-русски, длины в мм. Application checkpoint,
pending/returned native-step journal, полный post-release sketch/BREP/session
proof, exact plane/frame/dependency/external/annotation/anchor inventory.
Восстановление выдавливания сохраняет baseline sketch; неопределённые native,
storage/reference/foreign effects удерживают unknown без inverse/retry.

## Привязка и проверки

- Git: `b2cfa7a49c1ebbd44057a69187e100afab4b0854`, clean build.
- Версия: `2.0.0.dev90`.
- Source digest: `5675575dad26bc3f043fd9aafbc7c3fb6187fbacaf2299d1b70354e1bae898ca`.
- Wheel SHA256: `1586c9cc42f92b2f62c24f6d2c95286649b3c13614aeb3fbd3ab930dfb850a9c`.
- Full pure: **6390 passed /323 CAD deselected, 139,96 с**.
- Related facade/runtime294 passed, 13,28 с; artificial SDK + actual MCP/JobStore.
- Wheel gate и installed metadata79/25 accepted, output schemas/provenance проверены.
- Installed adapter MRO подтверждает новые construction/snapshot mixins;
  конструктор/COM не вызывался. Это не свидетельство CAD-операции.

Первый full6389/1 failed: версия registry template отставала, metadata исправлена
и обязательный full повторён. Первая команда `python -m build` не запустилась,
модуль build не установлен. Wheel успешно собран имеющимися pip/setuptools:
`--no-index --no-deps --no-build-isolation`. Registry/PyPI не публиковались.

Private evidence: `work/pytest-dev90-full-2.log`, `work/wheel-dev90-report-1.json`,
`work/metadata-dev90-report-1.json`; CAD/SQLite/полные журналы вне Git.

## Остаток B1

Все пять native-условий остаются: отдельная create→plane→sketch→extrude
40×20×10/8000; точная plane/сосед; русские имена/ID; stale/replay/отказы;
own restoration либо unknown/hold. Internal покрывает подробные отказы,
public MCP — пользовательскую цепочку и контракт того же wheel. L3 dev89
не подменяет native dev90. Стадия1 открыта: B1…B5.

## Начало native-приёмки

Подготовлен внешний `verify_rectangle_stages_positive.py`: отдельный sketch
без тела → extrusion по returned ID, replay каждой записи, независимый native
BREP/объём8000 и dirty сосед, exact-owned cleanup и baseline. Это только
положительный finite scope, `accepted=false`; N4/N5 и public MCP остаются.
Detached gate проверяет actual checkpoint/revision/guard/step ledger/result ID
и full primitive geometry admission. Related80 pure passed4,86 с; первоначально
исправлены синтаксис gate и неверные operation names искусственной fixture.
Обновлённые helpers не меняют executable wheel/digest.

Installed positive dev90 запущен одним CAD-владельцем;
`work/native-rectangle-dev90-positive-1/report.json`. Read-only
`sketch.prepare_rectangle` завершилась succeeded; теперь выполняется
`sketch.create_rectangle`. Native-успех записи не объявляется. New-part setup имеет
только exact normal creation returns; unknown/pending сохраняют процесс/receipts,
никакой roster-adoption или повторной COM-записи нет.

Независимая public payload обвязка подготовлена отдельно; related62 pure
passed3,63 с без CAD/SDK startup. Общие supervisor helpers работающего процесса
не меняются до его завершения. Нового push/CI нет.
