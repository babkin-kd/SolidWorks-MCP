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

Отдельный `verifier_rectangle_restoration.py` проверяет scoped rollback:
actual application checkpoint/revision, оба released guards, paired native
ledger, full baseline/dirty/files/sketch возврат и terminal failed/rolled_back.
Missing counters/fields, чужая дельта и pending/unknown не разрешают очистку.
Related78 source pure passed5,38 с на real JobStore/coordinator + artificial
CAD. Первый rollback-fixture прогон ошибочно повторно использовал уже созданную
искусственную модель; заменён свежим fixture, production code не менялся.
Это не native N5. Native positive продолжает тот же процесс/журнал; пока
sketch.create_rectangle running, итог не принят.

Добавлен `verifier_rectangle_prewrite.py`: exact request/code, failed с
`requires_reconciliation=false`, без checkpoint. Он не подменяет native
no-dispatch/full-baseline proof и не принимает not_started/rollback/unknown
без отдельного gate. Совместные98 artificial pure passed6,00 с.
Положительный native процесс подтвердил returned open/draw/define/close/rebuild
sketch steps и guard release; post-release independent проверка ещё running.
До committed/owned cleanup результат не засчитывается.

## Первый native positive: unknown и подтверждённая очистка

Dev90 positive завершил `sketch.create_rectangle` как **unknown/unresolved**,
1654,61 с. Actual sketch open/draw/define/close/rebuild и guard release вернулись
нормально; независимая проверка отвергла незаявленную display delta. Появился
второй пустой assigned annotation view (`shown=false`, `unassigned=false`);
старый view/light data и поддержанная сессия сохранены. Это не accepted B1
и не основание игнорировать display_data. Extrusion/public/N4/N5 не выполнялись.

После terminal jobs, полного paired ledger и отсутствия live COM владение
проверено по recorded HWND + полным snapshots/PID. Отдельный own-retirement
закрыл только две контрольные детали. Baseline/application/non-STL settings
восстановлены; retirement report accepted/terminal, SHA256
`8297644b31cde777529c6873274afa85eb15fcaf0b691f43e1ce255d5052e7bb`.
Private unknown согласован как accept_current_state по exact-owned retirement:
job status **unknown сохранён**, mutation phase=reconciled. Это не success CAD.

Retained verifier держал STA-подписки в sleep-loop без PumpWaitingMessages;
после передачи проверенного владения завершён только этот неисполняющий COM
helper, активный cleaner не прерывался. Cleaner завершился exit0. Будущий
retained loop исправлен: только PumpWaitingMessages/sleep, без повторной CAD-записи.

Добавлено чистое admission `rectangle_annotation_views.py`: новый view допускается
только при сохранных native view incarnations и независимой привязке обоих
sketch driving dimensions. Scalar lookalike без bindings отвергается; lights,
старые views/metadata сохраняются. Related18 pure passed0,13 с (17 view cases
и retained-STA проверка). Native bindings/reader и runtime-интеграция ещё
отсутствуют; установленный dev90 не менялся. Getter принадлежности определён
в [IAnnotation.AnnotationView](https://help.solidworks.com/2023/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IAnnotation~AnnotationView.html).
Нужен исправленный кандидат и новая native-приёмка; старый unknown не повторяется
и не переписывается. Все private CAD/журналы/retirement evidence остаются вне Git.

## Source исправление после unknown

Добавлены passive native bindings вида к actual driving dimension annotations
через IAnnotation.AnnotationView и bounded STA incarnation cache. В rectangle
snapshot появились typed sidecars; base oracle first-save сохранён отдельно.
Новый sketch view допускается только для width/height, новый extrusion view —
только для depth; baseline views/lights/old dimension bindings неизменны.
Cache освобождается на owning STA при закрытии адаптера.
Related335 pure passed14,11 с, `work/pytest-rectangle-view-final-1.log`.

Private interop probes 1 fixture каждый подтвердили getter/membership и
own-cleanup/baseline. Они не являются native acceptance инструмента. Geometry
inverse удалил body, но оставил все3 annotation views. У IAnnotationView
нет delete/select метода в установленном SDK; IFeature.Name через этот объект
дал DISP_E_MEMBERNOTFOUND, MultiSelect2 raw views дал0. N5 exact-owned view
retirement ещё нужен; нельзя пропустить metadata либо удалять по именам/дельте
списка без native ownership. Установленный wheel dev90 неизменен, нового CI нет.
