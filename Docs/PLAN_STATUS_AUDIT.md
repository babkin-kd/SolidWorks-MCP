# Аудит статусов плана — актуализация 12.10.2026

## Текущий итог

Стадия 1 открыта: L2 принят в ограниченном scope dev87; **остаются шесть
блоков L3 и S1-B1…S1-B5**. S1-B5-ACT принят отдельно на dev89 (четыре
внутренних случая и public MCP/native); saved-file интеграция L3-P1 и сквозной
B5 не приняты. Внутренние L3-I1…I4 приняты на dev88, а не автоматически на dev89.
Следующий L3-P1 требует internal/public свидетельств одного точного wheel.

Минимальный результат, поддержанные случаи и конечные критерии каждого блока
зафиксированы в [плане](../PLAN.md), [матрице](STAGE_1_REQUIREMENTS_MATRIX.md)
и [приёмке](STAGE_1_BLOCK_ACCEPTANCE.md). Обязательные гарантии не перенесены;
все 22 прежних требования прослеживаются, 20 расширений остаются видимыми
отдельными задачами стадий 2/3. Ограниченная приёмка открытия не расширяется.

Для этого пересмотра повторно прочитаны финальные private отчёты L2: accepted,
13/11 случаев, точные опубликованные SHA256, own cleanup и baseline совпали.
Повторный CAD-прогон, новый wheel и отдельный push ради документации не требуются.
Пакет отправлен одним push9489360 в draft PR15. Remote CI38193016491
завершился success: unit/build/installed metadata прошли; прежний CI failure
сохранён в истории. Merge/main не выполнен. [Пакетная сводка](CHECKPOINT_DEV89_BATCH.md).
Native L3-I1 dev89 прошёл980,22 с: committed/full readback/mapping41,
131 captures returned, own cleanup/baseline и текущие hashes подтверждены.
L3-I2 этого wheel запущен отдельно, ещё не принят; общий L3/P1 остаётся открыт.
[Точные факты L3](NATIVE_FIRST_SAVE_PROGRESS.md).

GitHub-задачи №1–4 синхронизированы напрямую через API с опубликованной
матрицей: конечные results/scopes/gates, обязательная safety и видимые переносы.
Повторное чтение API подтвердило все четыре open/milestone1 и ссылки на матрицу.
История ранних dev2/dev3 сохранена; ни одна задача не закрыта по CI.

## Хронология приёмки до текущего итога

Следующие записи сохраняют состояние на момент своих контрольных точек;
прежний статус «ACT открыт» заменён фактическим итогом dev89 выше.

L2 bounded native open принят на exact installed dev87: metadata71/21,
internal13/13 (210,07 с), public MCP11/11 (189,68 с), оба accepted=true.
Полный source pure5560 passed/323 CAD deselected (77,43 с); external cleanup
regressions — related499 passed (1,15 с). Полный baseline/CWD, dirty сосед,
resolved new/borrowed references и own cleanup подтверждены. Исторические
failed/unknown отчёты сохранены; они не переписаны и не повторены.
[Точная приёмка](NATIVE_DOCUMENT_OPEN_ACCEPTANCE.md),
[контракт](NATIVE_DOCUMENT_OPEN.md).

Пересмотр границы выпуска по решению пользователя: L2/L3/S1-B1…S1-B5;
после L2 остаются шесть конечных блоков. Один public same-wheel сценарий
create/sketch/extrude/edit/first save/close/open/edit/Save3/close при dirty соседе
закрывает S1-B5 после профильных gates. Все22 прежних требования прослеживаются,
20 расширений остаются отдельными незавершёнными задачами стадии2/3.
[План](../PLAN.md), [матрица](STAGE_1_REQUIREMENTS_MATRIX.md),
[конечная приёмка](STAGE_1_BLOCK_ACCEPTANCE.md).

Уточнён порядок шести остатков: L3 → S1-B1 → S1-B2 → S1-B3 → S1-B4 → S1-B5.
L2 не расширяется; same-wheel финал остаётся обязательным. Для L3/сквозной
цепочки baseline ограничен полностью наблюдаемой самостоятельной контрольной
part того же профиля; иной неподдержанный сосед даёт отказ до записи.
Обязательные гарантии применяются с первого блока, а не с момента приёмки B4.
Устранён устаревший статус «отбортовка в работе» в разделе2.2: dev67/dev68
остаются историческими scoped приёмками. Требование производственного DXF
видимо, но выполнение зависит от возврата отложенного D-DEFER-IMPORT.

Обязательны explicit target/revision/request_id, полный supported checkpoint,
STA/durable ledger/holds, no retry unknown, реальные postconditions и native
точного wheel. Сужение продуктового scope не ослабляет эти гарантии.
L3 находится в исходной реализации: домен/one-shot bridge и passive oracle
интегрированы в runtime и публичный исходный каталог двумя инструментами.
Связанные domain/runtime/MCP/stdio pure366 passed/26,07 с; нового wheel ещё нет.
Native source Copy-прототип3 принят:
35,15 с, source/clone full proof,41 mappings, dirty сосед и own cleanup/baseline.
Связанный новый source-набор289 passed/11,98 с; прежние419 относятся к своей
контрольной точке. Прототип2 failed из-за изменения активного AutoSelect на
legacy-основании; его исход не переписан. Новый v2 base создаётся без scope
предсуществующих тел, недоступный getter и document qualifications наблюдаются
явно. Составной source CAD/NTFS-прототип1 прошёл за44,28 с: строгие leases
совместимы с Copy/readback, no-replace publication, writable final,41 mappings
и source retirement; cleanup/baseline=true, pending=false, owned=[], leases
освобождены. Эти самостоятельные прототипы не подтверждали native UI guards
и журнал полного домена; нынешняя полная source-проба описана ниже. Installed
фасад и same-wheel native остаются; source experiment не закрывает L3.
[Фактическое продвижение и оставшиеся gates](NATIVE_FIRST_SAVE_PROGRESS.md).
Full source domain probe1 — unknown после нормального source close,988,76 с.
Точное первоначальное расхождение не сохранено; независимый разбор подтвердил
полный clone/file и сосед, затем own cleanup и empty baseline приняты отдельно.
Журнал unknown сохранён. Canonical snapshot/strict bool-int clone comparison,
exact-final activation и durable mismatch evidence исправлены; related278 pure
passed/20,23 с. Full source domain probe2 прошёл за994,58 с: job succeeded/committed,
24 native ledger rows прошли отдельный predicate; независимый full CAD readback,
mapping41, writable final, dirty сосед и own cleanup/baseline подтверждены.
Native_calls_live=false, owned=[]; прежний unknown не переписан.
Текущий полный source pure5973 passed/323 CAD deselected,99,38 с; related
metadata/runtime/MCP44 passed/4,56 с. Новый installed verifier ожидает73 tools/22
mutations. Dev88 теперь собран/установлен, итоговый source pure5978/323 CAD
deselected (99,46 с), installed metadata/stdio73/22 accepted. Installed L3-I1
прошёл за1008,63 с: committed, 24 ledger rows verified, independent full
readback/mapping41, cleanup/baseline. L3-I2 прошёл за686,00 с: existing/stale,
Copy0 и own cleanup/baseline. L3-I3 прошёл за874,27 с: actual collision/no-overwrite,
known rollback, foreign bytes/identity, replay и cleanup/baseline. L3-I4 warning
прошёл за757,28 с: unknown/hold/replay, independent clone41/readback,
exact own reconciliation и baseline; historical unknown не success. L3-I4 false
прошёл за756,52 с: unknown/hold/replay, clone41, stage retention и exact
reconciliation/empty baseline. Throw прошёл за757,30 с: unknown/hold/replay,
clone41, source/neighbor/stage preservation и reconciliation/empty baseline.
Incomplete прошёл за726,39 с: normal native Copy, bridge-инъекция,
unknown/hold/replay, independent clone41, exact reconciliation и baseline.
12.10.2026 общий detached preflight всех семи внутренних отчётов dev88 прошёл:
точный wheel/source и текущие helper hashes подтверждены. Public/S1-B5-ACT открыты.
Дополнительно выявлен S1-B5-ACT: open восстанавливает active сосед, dimension edit
требует active target; ручная активация не засчитывается как MCP automation.
L2 scope не расширяется. Первый JSON-сбой L3-I2
после создания пустой part сохранён, own cleanup/empty baseline подтверждены
отдельно; 15 pure-регрессий (0,60 с) проверили scalar projection и creation DTO.
L3 и конечные native/public gates открыты.
[Точный артефакт и проверенные факты](CHECKPOINT_DEV88.md).
Remote CI последнего пакета failure; локальное исправление входит в pure,
нового push нет. Исторические свидетельства ниже не являются приёмкой dev87
или итоговой стадии1; прежние «20 из22» не используются как текущий gate.

## Решение о границе выпуска — 12.10.2026

L2 завершён без изменения контракта или manifest. Минимальный рабочий сценарий
и обязательные гарантии отдельно сформулированы в PLAN.md. Для каждого из
шести остатков матрица задаёт результат, поддержанные случаи, конечные условия
и конкретный блокер. S1-B5-ACT виден отдельной незавершённой задачей. История
плана вынесена в PLAN_HISTORY.md; все22 S1-ID, legacy migration и20 D2/D3 задач
сохранены. Перенос не означает passed. Новый wheel/CAD/CI ради документации
не запускался; GitHub push не выполнялся, изменения накоплены локально.

## История до пересмотра границы выпуска

Dev85: clean native close принят:4673 pure перед wheel; final пакет4677/323 CAD deselected (60,07с). Installed metadata69/20,
internal12/public MCP10 accepted=true на одном точном wheel. Полный retirement
assembly+explicit hidden collateral, part/drawing, dirty сосед, replay/stale,
explicit survivor activation и empty/free baseline подтверждены.
[Контракт](NATIVE_DOCUMENT_CLOSE.md), [приёмка](NATIVE_DOCUMENT_CLOSE_ACCEPTANCE.md).
First save/open, dirty-owned/retained-reference close и общий N6 остаются;
стадия1 открыта,20 из22 требований по-прежнему открыты полностью/частично.
Прежние scoped результаты привязаны к своим wheel; legacy20/20 отдельно.


Dev82: сохранение существующего native-файла детали/сборки/чертежа принято:
4455 pure/323 CAD deselected перед wheel (55,56 с); после изменения общего
verifier и добавления69 pure-регрессий итоговый пакет4524 passed/323 deselected
(59,92 с). Installed metadata67/19, internal native10/public MCP5 accepted=true
на одном точном wheel. Перечитывание трёх типов файлов, сохранность dirty
referenced child, replay/stale и exact-owned cleanup/baseline подтверждены.
[Контракт](NATIVE_DOCUMENT_SAVE.md), [приёмка](NATIVE_DOCUMENT_SAVE_ACCEPTANCE.md).
Первое сохранение и публичные open/close остаются обязательными S1-15;
[проект следующего блока](NATIVE_DOCUMENT_LIFECYCLE_DESIGN.md).
Стадия1 открыта;20 из22 требований остаются открытыми полностью/частично.
Legacy20/20 — отдельный source-пилот, не приёмка v2.

Исторический dev79: расстояния от полного solid-агрегата part/subassembly до точки
и бесконечной оси приняты:4409 pure/323 CAD deselected (57,25 с), installed
metadata65/18, internal native24/public MCP8 accepted=true на одном wheel.
Exact4-owned cleanup, пустой/free baseline и non-STL preferences подтверждены.
Hidden cylinder3/6/0 мм для точки и2/0 мм для оси, explicit rigid frame,
native configuration replacement, multibody3/2 и replay проверены.
[Контракт](COMPONENT_AGGREGATE_PROBES.md), [точная приёмка](COMPONENT_AGGREGATE_PROBES_ACCEPTANCE.md).
Native named frames, остальные состояния/измерения сборок, масштаб1000+
и общий N0–N6 остаются. Следующий обязательный блок — native open/save/close
S1-15. Стадия1 открыта, расширения2 отложены; legacy20/20 учитывается отдельно.

Исторический dev78: расстояние между полными solid-агрегатами part/subassembly принято:
4365 pure/323 CAD deselected (54,78с), installed metadata63/18,
internal native19/public MCP6 accepted=true на одном wheel. Exact4-owned
cleanup, пустой/free baseline и non-STL preferences подтверждены. Полный
leaf census/все пары, hidden cylinder minimum84 мм, shared descendant0,
explicit rigid frame, native смена конфигурации/rename/move проверены.
[Контракт](COMPONENT_AGGREGATE_DISTANCE.md), [точная приёмка](COMPONENT_AGGREGATE_DISTANCE_ACCEPTANCE.md).
На момент dev78 point/axis distance агрегатов, native named frames и общий N0–N6 оставались;
S1-06/S1-16 и стадия1 открыты. Legacy-пилот учитывается отдельно.


Исторический dev77: расстояние resolved экземпляра детали до бесконечной оси принято:
4335 pure/323 CAD deselected (54,63с), installed metadata62/18,
internal native18/public MCP6 accepted=true на одном wheel; exact4-owned
cleanup, baseline и non-STL preferences подтверждены. Exact directional
supports + memory-only wire, hidden/rotated/nested instances, oblique axis,
explicit rigid frame, far origin/reversed direction, cylinder surface gap/tangency.
[Контракт](COMPONENT_AXIS_DISTANCE.md), [точная приёмка](COMPONENT_AXIS_DISTANCE_ACCEPTANCE.md).
На момент dev77 aggregate subassembly, named native frames и общий N0–N6 оставались;
S1-06/S1-16 и стадия1 открыты, расширения2 отложены. Старые приёмки ниже
относятся к их wheel и не засчитываются в итоговый gate текущего кандидата.

Исторический dev76: point boundary distance/native location для resolved part instance принят:
4287 pure/323 CAD deselected (53,93с), installed metadata61/18,
internal native19/public MCP6 accepted=true на одном wheel; exact4-owned
cleanup, baseline и non-STL preferences подтверждены. Hidden rotated
inside/outside/boundary, explicit frame/trimmed corner, nested/multibody,
solid cylinder и hollow cavity/material, old replaced body/face rejection.
[Контракт](COMPONENT_POINT_DISTANCE.md), [точная приёмка](COMPONENT_POINT_DISTANCE_ACCEPTANCE.md).
На момент dev76 axis distance, aggregate subassembly targets, named native frames и общий
N0–N6 остаются; стадия1 открыта, расширения2 отложены.

Dev75: расстояние между двумя resolved экземплярами деталей принято:
4236 pure/323 CAD deselected (53,88с), installed metadata60/18,
internal native13/public MCP6 accepted=true на одном wheel; exact-owned cleanup
и baseline подтверждены. Hidden rotated/multibody15 мм, nested70 мм,
curved overlap/tangent0, native move14 мм, cylinder gap24 мм вместо axis36 мм.
[Контракт](COMPONENT_DISTANCE.md), [точная приёмка](COMPONENT_DISTANCE_ACCEPTANCE.md).
На момент dev75 S1-16/S1-06 частично: point/axis distance, агрегат подсборки, native named
frames и общий N0–N6 остаются; стадии1/2 не объявлены завершёнными.

Срез локального проекта: исходники кандидата `2.0.0.dev67`, Git `01a764b23a5549c07c94111fa4ace8facb9ab989`. Аудит выполнен чтением плана, кода, тестов и существующих отчётов; новые тесты, сборки, CAD-вызовы и GitHub CI не запускались. Основная разработка продолжается, поэтому дальнейшие результаты должны обновить этот срез. Приватные CAD/журналы/отчёты не копировались в публичную документацию.

## Актуализация после исходного среза — 11.10.2026

Отбортовка dev67 завершена:3897 pure/323 CAD deselected, metadata46/16,
internal8/public7 accepted=true на одном wheel; [точный результат](SHEET_EDGE_FLANGE_ACCEPTANCE.md).
Все задания terminal, own fixtures закрыты, пуст/free baseline, новых unknown нет.
Dev68:3997 pure/323 CAD deselected, installed metadata48/17; U internal9/public10 accepted=true на одном wheel,
own cleanup и baseline подтверждены; [свидетельство](SHEET_FLANGE_FLAT_ACCEPTANCE.md). Metadata не подтверждает физический результат.

По новому решению пользователя работа возвращается к остаткам стадии1:
[конечная матрица22 требований, проверок и блокеров](STAGE_1_REQUIREMENTS_MATRIX.md).
Пользователь11.10.2026 зафиксировал базовый инвентарь31 legacy-пункт
(документы/адресация/эскизы/плоскости/базовое выдавливание/размеры/удаление/
подавление/измерения/диагностика). Обязательные gates не сокращены.
Диагностика стадии 1 реализована в исходниках:34 новых timing pure passed,
контракт и границы — [DIAGNOSTICS_TIMINGS.md](DIAGNOSTICS_TIMINGS.md).
Dev69 metadata49/17/stdin/native20 reads/internal4 basic accepted=true;
[приёмка](DIAGNOSTICS_TIMINGS_ACCEPTANCE.md). Config/storage пункт1.5 принят;
общие фазы/geometry grouping/performance и стадия1 остаются открытыми.
Dev71: публичная масса детали — metadata51/18,4072 pure/323 CAD deselected,
internal22/public6 accepted=true на одном wheel; exact-owned cleanup и baseline
подтверждены. [Приёмка](MASS_MEASUREMENT_ACCEPTANCE.md). S1-16 частично: bounds,
distance, assemblies/custom frames и общий gate остаются.
Dev72: габариты детали в явных rotated/shifted axes, metadata52/18,4122 pure/
323 CAD deselected, internal14/public6 accepted=true на одном wheel; cleanup/
baseline подтверждены. [Приёмка](BOUNDS_MEASUREMENTS_ACCEPTANCE.md). Distance,
assembly/component/native named frames и общий gate остаются.
Новые расширения2.1/2.2 не начинать до закрытия стадии1.

Dev74: normal instance face/edge topology принято:4210 pure/323 CAD deselected,
metadata59/18, internal21/public8 accepted=true на одном wheel; cleanup/baseline.
[Приёмка](COMPONENT_TOPOLOGY_ACCEPTANCE.md). Hidden/curved BREP, native rename/delete/recreate guards доказаны;
прочие состояния, измерения сборок и общий S1/final gate остаются открытыми.


Dev73: адресация resolved экземпляров сборок и normal solid/surface тел принята:
4175 pure/323 CAD deselected, metadata56/18, internal15/public6 accepted=true
на одном wheel; exact-owned cleanup/baseline подтверждены. [Приёмка](COMPONENT_READS_ACCEPTANCE.md).
S1-04/S1-05/S1-06 частично: topology/прочие состояния/deleted refs/измерения
сборок и общий финальный gate остаются. Стадия1 открыта, расширения2 отложены.
 Исходный срез ниже
сохранён как история; сведения о ещё running dev67 не являются текущим итогом.

## Как читать статусы

- **Готово:** указанное требование реализовано и имеет подходящие подтверждения в указанной области. Не означает приёмку всей стадии или всех CAD-операций текущего wheel.
- **Частично:** есть реализация/проверка части требования, но остаются функции либо необходимая приёмка.
- **Реализовано, не принято:** кандидат есть, но нужная native/MCP-приёмка не завершена или неуспешна.
- **Не начато в v2:** нет подтверждённого прикладного блока нового API. Legacy-задел может существовать.
- **Отложено:** функционал сохранён в плане на позднюю стадию.

Процент готовности по числу галочек не вычисляется: пункты сильно различаются по объёму, а наличие кода, чистый wheel и приёмка реальной операции — разные результаты.

## Основные выводы

1. В 1.2 уже есть значительная реализация. Пустые галочки скрывали разделение слоёв, STA, явные документы, ссылки, единицы и общий ответ. Полная заявленная область, особенно сборки/конфигурации/поверхности, не принята.
2. Незакрытый 1.1 смешивает локально готовый контур проверки с будущей публикацией. Локальная разработка возможна, но GitHub CI и выпуск нельзя считать подтверждёнными локальными логами.
3. Стадия 1 не завершена. При этом отдельные блоки 2.1 и 2.2 уже фактически разрабатываются/принимаются. Это отклонение от строгого порядка «стадия 2 после приёмки стадии 1», а не доказательство завершения основы. Аудит фиксирует факт, не разрешает формальный переход и не меняет критерии приёмки.
4. По 1.5 выполнены контрольные замеры и оптимизация dev55; общей функции статистики вызовов нет. Нельзя объявлять весь пункт выполненным по ускорению одного сценария.
5. В PLAN.md раздел ближайших действий и исторические абзацы содержат устаревшие «следующие шаги». В MIGRATION_V2.md встречаются разные исторические числа 18/26/30 и «текущее состояние dev27», в FORK_RELEASE.md — статическое число 18. Их нужно читать как историю, а не актуальный каталог. Актуальный metadata-каталог dev67 — 46 инструментов; принятая цепочка dev63 — 44 инструмента/15 мутаций.
6. В 2.2 ошибочно смешивались низкий приоритет общего обмена и производственный DXF. По принятому плану минимальный DXF развёртки остаётся в 2.2; общий импорт/экспорт — 3.4. Статус-пояснение в плане уточнено, требования не удалены.

## Проверенные свидетельства

| Свидетельство | Что подтверждает | Чего не подтверждает |
| --- | --- | --- |
| `server_v2.py`, `*_tools_v2.py`, `runtime_v2.py`, доменные модули и `cad_*` | Реальную структуру и регистрацию кандидата; отдельные адаптеры/контракты | Фактическую работу всех инструментов в SolidWorks |
| `com_worker.py`, `documents.py`, `geometry.py`, `contracts.py`, `jobs.py` | Один STA runtime v2, идентичности/явный контекст, ссылки, общий ответ, durable-задания | Общий координатор двух независимых процессов v1/v2 или универсальную ревизию любой модели |
| `tests/test_com_worker.py`, `test_jobs.py`, `test_application_mutation_holds_v2.py` и доменные тесты | Наличие проверок lifecycle, тайм-аутов, отмены, перезапуска, holds и доменных сценариев | Native-приёмку аварий/перезапуска CAD-процесса; в аудите эти тесты не перезапускались |
| `.github/workflows/ci.yml`, `Docs/FORK_RELEASE.md` | Локальный workflow pure/build/installed metadata; унаследованной автоматической публикации нет | Актуальный успешный GitHub Actions run или согласованный публичный выпуск |
| Metadata-отчёт установленного dev67 | `accepted=true`, 46 инструментов, outputSchema и совпадение установленного wheel с build metadata | CAD-приёмку отбортовки: отчёт metadata не вызывает CAD/job-инструменты |
| Internal/public отчёты dev60, dev61, dev62, dev63 | Принятые ограниченные цепочки скругления, L-профиля, flat/fold и листовых параметров | Совокупную приёмку этих возможностей на новом dev67 |
| Internal/public параметры dev63 | Оба `accepted=true`, 8/10 случаев, совпадающие Git SHA и source digest точного wheel | Отбортовку, несколько тел/конфигураций и прямую запись параметров развёрнутой детали |
| Отчёты отбортовки dev64–dev66 | `accepted=false`, известные точки остановки, сохранённые неопределённые исходы | Успешную приёмку по наличию созданной U-формы или последующей очистке |
| Отчёт отбортовки dev67 на момент чтения | Незавершённый прогон: `accepted=false`, без записанной итоговой ошибки | Итоговый отказ или успех; незавершённый отчёт не является отрицательным итогом |
| `ENGINEERING_BENCHMARKS.md` | Контрольные времена, ограничения счётчиков COM и сравнение dev54/dev55 | Постоянный сбор статистики по этапам или p95 опытной эксплуатации |

Приватные отчёты лежат в ignored `work/`; здесь приведены только обезличенные выводы. Связанные публичные контракты: [API_V2](API_V2.md), [SHEET_PROFILE](SHEET_PROFILE.md), [SHEET_FLAT_STATE](SHEET_FLAT_STATE.md), [SHEET_PARAMETERS](SHEET_PARAMETERS.md), [SHEET_EDGE_FLANGE](SHEET_EDGE_FLANGE.md), [ENGINEERING_BENCHMARKS](ENGINEERING_BENCHMARKS.md).

## Стадия 1: статус каждого пункта

Номер после раздела — порядковый номер checkbox в этом разделе PLAN.md.

| Пункт | Статус | Реализовано / что осталось |
| --- | --- | --- |
| 1.1 / 1 — форк и remotes | Готово по существующим записям проекта | Форк/ветка заведены; удалённые ресурсы заново через GitHub в этом аудите не проверялись |
| 1.1 / 2 — история и локальная база | Готово по существующим записям проекта | История сохранена; аудит её не менял |
| 1.1 / 3 — план, milestones, задачи | Готово по существующим записям проекта | PLAN и ссылки на задачи есть; текущие статусы удалённых задач не перепроверены |
| 1.1 / 4 — отдельный wheel и metadata | Готово | Реальные installed metadata-прогоны; dev67 совпадает с точным wheel. Это не общий CAD-gate |
| 1.1 / 5 — проверки и выпуск | Частично | Локальный artifact-only контур готов. Остались актуальный GitHub CI, собственное имя публичного пакета и согласованный выпуск |
| 1.2 / 1 — разделение слоёв | Частично | MCP/domain/CAD/runtime/jobs разделены для перенесённого v2. Остались миграция базовой области и диагностика времени |
| 1.2 / 2 — один STA | Готово для runtime v2 | Очередь/pump/thread checks/finalizers есть, поддерживаемые цепочки прошли native/MCP. Координация независимых v1/v2 — отдельная задача |
| 1.2 / 3 — явный контекст | Частично | Документ/активная конфигурация/объекты есть. Остались component paths и общая приёмка многоконфигурационных моделей/сборок |
| 1.2 / 4 — устойчивые ссылки | Частично | Read-каталог solid/surface и persistent references, stale/ownership checks есть. Осталась полная native-область поверхностей/многотельности/сборок |
| 1.2 / 5 — единицы/координаты | Частично | Мм/градусы/кг, SI conversion, явные плоскости/оси поддержанных сценариев есть. Произвольные координатные системы и остальной scope не приняты; импорт проверяется в 3.4 |
| 1.2 / 6 — общий ответ/постусловия | Частично | ResponseEnvelope/outputSchema и полные постусловия поддержанных операций есть. Осталась общая приёмка исходных/новых rebuild-дефектов и новых инструментов |
| 1.3 / 1 — request_id/полная ревизия | Частично | Реализовано в поддержанных мутациях. Общие ручные изменения/несколько конфигураций/вся базовая область ещё не приняты; document observation token не заменяет mutation revision |
| 1.3 / 2 — durable SQLite jobs | Готово для модели заданий v2 | Состояния и независимый опрос есть; новые CAD-операции требуют своей приёмки |
| 1.3 / 3 — идемпотентность/поздний результат | Готово для модели заданий v2 | Контроль request conflict/дубликата, late completion покрыт pure; повтор request_id проверен native/MCP в ограниченных цепочках |
| 1.3 / 4 — отмена/restart unknown | Готово для модели заданий v2 | Queued-only cancel, восстановление незавершённых заданий в unknown без replay покрыто pure. Не является native crash-приёмкой стадии |
| 1.3 / 5 — checkpoint/восстановление | Частично | Приняты собственные creation/scalar restoration. Отбортовка dev67 принята на своём wheel; совокупная общая область не принята; generic Undo не подтверждён |
| 1.3 / 6 — holds после uncertain | Частично | Document/application holds и сохранение unknown есть, использованы при реальных остановках. Осталась общая installed/native проверка restart/reconciliation |
| 1.4 / 1 — preview/удаление | Частично | Internal graph/structure/context и часть внешних привязок есть. Нет полного impact preview и публичного execute; уравнения/конфигурации/аннотации/incoming refs остаются |
| 1.4 / 2 — размеры | Частично | Приняты отдельные размеры эскиза/основания/отверстия/листа. Общие размерные типы, знаки/допуски и произвольная история ещё не приняты |
| 1.4 / 3 — русские названия | Частично | Имена/readback есть в принятых цепочках. Остаётся общая выпускаемая область; сборки/стандартные библиотеки ещё впереди |
| 1.4 / 4 — ускорение captures | Частично | Контрольные оптимизации dev27/dev49/dev55 измерены, полные границы сохранены. Это не performance-приёмка всех моделей/больших сборок |
| 1.4 / 5 — миграция базовых операций | Частично | Документы/геометрические чтения/часть эскизов/деталей перенесены. Публичный mass backend, другие базовые операции и актуальная сводная MIGRATION_V2 не завершены |
| 1.5 / 1 — время по этапам | Частично, измерительный задел | Есть timestamps jobs и внешние controlled timings; общего монотонного сборщика queue/prepare/COM/rebuild/postconditions/restoration/logging нет |
| 1.5 / 2 — безопасные записи вызовов | Частично, журнальный задел | Durable jobs есть; отдельного обезличенного performance-record и разделения polling/CAD ещё нет. Нельзя использовать полный job payload как безопасную телеметрию |
| 1.5 / 3 — настройка/retention/изоляция сбоев | Не начато | Отдельный настраиваемый ограниченный performance-журнал не реализован |
| 1.5 / 4 — diagnostics_get_timings | Не начато | Инструмента нет в исходном/установленном каталоге; медиана/p95 по периоду не выдаются |
| 1.5 / 5 — пилот и одна оптимизация | Готово в ограниченном эксперименте | Замер и guard-оптимизация dev55 приняты; не постоянная статистика опытной эксплуатации и не закрытие 1.5 целиком |

### Критерии закрытия стадии 1

| Критерий | Статус | Остаток |
| --- | --- | --- |
| Два документа, конфигурации, многотельность | Частично | Сохранение второй детали проверено. Общая многоконфигурационная/многотельная мутация не подтверждена |
| Stale/ручное изменение/неверная ревизия | Частично | Stale-гейты приняты в цепочках. Нужна общая матрица ручных изменений и ссылок в полном выпускаемом scope |
| Rebuild-ошибки и восстановление новых/существующих операций | Частично | Injected known failure/создание/scalar rollback есть. Нужны реальные ошибки rebuild и завершённая общая матрица; flange dev67 принята, общий rebuild-gate открыт |
| Late result/request_id/restart | Частично | Сильные pure-проверки и native идемпотентность есть. Общая приёмка restart с незавершённой операцией на установленном пакете не подтверждена |
| Каталог/stdio/wheel/schema | Готово для dev67, metadata-only | Подтверждены 46 инструментов и build/schema; новые кандидаты проверяются заново |
| Native в SolidWorks 2023 | Частично | Несколько исторических ограниченных цепочек приняты. Нет общего итогового кандидата с согласованным набором обязательных сценариев |
| Время/COM и повторные обходы | Частично | Есть конкретные замеры/оптимизации, часть dispatch-count имеет объявленные ограничения. Общий выпускаемый scope не измерен |

Оформление общего кандидата и актуальный CI/выпуск из 1.1 остаются открытыми. Развитие импорта/экспорта не добавляется к gate стадии 1. Не сокращать существующие критерии и не переносить их задним числом ради отметки «готово».

## Стадии 2 и 3

| Раздел | Статус | Принято / остаток |
| --- | --- | --- |
| 2.1 Детали | Частично | Отдельные основание/эскиз/cut/revolve/hole/edit/pattern/fillet приняты на своих wheel. Резьбы, произвольные профили, 3D/sweep/loft, исправление тел, boolean и перестановка дерева не приняты в v2 |
| 2.2 Листовой металл | Частично; flange dev67 принята, U dev68 pending | L/flat/fold/t-r-K приняты в dev61–dev63; flange принята в dev67. Явный K работает в этой области; профили предприятия, другие формы, прямое редактирование flat, несколько конфигураций, multi-body DXF и файловая часть остаются |
| 2.3 Сварные конструкции | Не начато в v2 | Нет принятого блока профилей предприятия/стыков/cut-list; legacy не засчитывается |
| 2.4 Чертежи | Не начато в v2 | Нет принятого ЕСКД/ГОСТ/template/BOM/specification/PDF блока |
| 2.5 Конфигурации/свойства/материалы | Не начато как прикладной блок v2 | Проверка активной конфигурации и scalar размеров — задел, не управление семействами/свойствами/материалами |
| 2.6 Сборки/стандартные библиотеки | Не начато в v2 | Нет принятого component/mates/library/1000+ блока |
| 2.7 PDM Professional | Не начато в v2 | Нет принятого моста/LoginAuto/get/check-out/check-in/version блока |
| 3.1 Кинематика | Отложено | Нет принятого v2-сценария траектории/зазоров/восстановления |
| 3.2 Печать/сетки | Отложено | Legacy mesh и экспортный задел не закрывают STL preference defect, 3MF и native-реконструкцию |
| 3.3 Simulation | Отложено | Нет принятого лицензированного native расчёта сборки с контактами |
| 3.4 Обмен файлами | Отложено; частичный legacy/v2 задел | Legacy импорт dev32 имеет историческую приёмку; v2 export код зарегистрирован. Новый импорт, расширение форматов и актуальная общая приёмка не выполняются сейчас; STL остаётся в 3.2 |

Критерии стадии 2 целиком не приняты: нет подтверждённых сценариев исправления импортированного тела, двухконфигурационной многотельной листовой детали с DXF, сварной рамы, корпоративного чертежа/PDF, сборки >1000, полного PDM-цикла и общей отрицательной матрицы. Не смешивать частичный листовой результат с производственной приёмкой.

## Рекомендуемый порядок после текущего блока

1. Довести начатую приёмку flange до известного конечного результата без вмешательства в выполняющийся COM; если scope не подтверждён, сохранить отказ/unknown и явно описать границу, не считать блок принятым.
2. Составить конечную матрицу остаточных gates стадии 1 на одном итоговом установленном кандидате: модели/конфигурации/ссылки, rebuild/restoration, late/restart/holds, metadata и установленный MCP. Различать pure, installed и CAD. Не запускать заново всю историческую CAD-матрицу без зависимости.
3. Устранить конкретные блокеры этой матрицы, включая недостающие базовые операции. Не расширять 2.1/2.2 бесконечно вместо закрытия первой стадии. Изменение области gates требует отдельного решения; аудит её не меняет.
4. Актуализировать сводную MIGRATION_V2 и близкие действия PLAN, отделив исторические результаты от текущего каталога. Сохранить историю и точные границы приёмок.
5. Отправить накопленный цельный пакет в форк через штатный PR/CI, затем оформить результат стадии 1 и согласованный выпуск. Локальный аудит не инициировал push/CI/release.
6. Продолжить формальную стадию 2 по принятому приоритету. Полный мониторинг 1.5 остаётся открытым; добавлять небольшой рабочий блок по плану, не превращать его в отдельный большой проект.

План обновлён статусами и пояснениями; исходники, версии, журналы и текущие native-проверки не изменялись. Обнаруженные проблемы учёта не объявляются исправленными в коде.


**Установленный кандидат dev89:** bounded S1-B5-ACT реализован в домене/runtime/MCP;
75 tools/23 mutations, full pure6075/323 CAD deselected (104,01 с).
Installed metadata/stdio75/23 принят без source PYTHONPATH. Положительный native
ACT-N1 прошёл (1027,38 с), ACT-N2 already-active прошёл (1018,36 с). Stale/foreign
прошёл (675,30 с); controlled failure прошёл (696,41 с). Actual four-report
preflight принят; public MCP/native ACT принят (2049,55 с). Сквозной
saved-file L3-P1/B5 ещё открыт, L2 не расширен, стадия1 не закрыта.
[Контрольная точка dev89](CHECKPOINT_DEV89.md).
