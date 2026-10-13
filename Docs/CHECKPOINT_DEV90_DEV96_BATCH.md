# Пакетная контрольная точка dev90–dev96

13.10.2026. Связанные изменения после опубликованного head
`9489360a6ff090b0c1f9514feb628d5d86339274` накоплены локально для одной отправки
в draft PR15 нашего форка. Base main —
`3ab795ec9d75e8a0055d41554cd439737b8b82f8`; актуальный fetch подтвердил, что он
уже входит в рабочую ветку. Main/merge/release не выполняются.

## Проверенные законченные части

- L3 native first-save/open/save/close dev89 принят: семь внутренних отчётов и
  public4/4; current baseline и собственная очистка подтверждены.
  [Точная привязка](NATIVE_FIRST_SAVE_DEV89_ACCEPTANCE.md).
- B1 dev94 принят: positive создание прямоугольного эскиза/основания и replay,
  finite faults7/7 и public5/5, SQL/independent snapshots/cleanup/root audit.
  [Точная привязка](B1_DEV94_ACCEPTANCE.md).
- B2 suppression/return positive dev95 принят отдельно:2/2,5594,79 с,
 129 terminal captures,8 succeeded jobs/4 committed mutations. Negative/public
  условия B2 этим positive не закрыты. [Привязка](CHECKPOINT_DEV95.md).
- B2 own-leaf positive dev96:leaf2/2,parent4/4,4136,97 с,112 returned captures,
 6 succeeded jobs/3 committed mutations; full SKETCH/neighbor, replay и
  own cleanup/root baseline приняты. Failed positive1 сохранён отдельно.
- B2 finite faults dev96:5/5,9137,84 с,196 returned captures; root audit actual
 SQL9 jobs/report/helper SHA/current empty baseline/non-STL preferences принят.
 Historical unknown остаётся unknown/unresolved, reconciliation=None.
  [Конечная матрица B2](B2_DEV96_ACCEPTANCE.md).

Результаты относятся к точным артефактам соответствующих версий. Приёмка
нескольких версий не заменяет итоговую same-wheel приёмку стадии1.

## Текущий installed кандидат

Version `2.0.0.dev96`, build Git
`f80ee6d80819140a8122fcf26104b0ce6760bff8`.
Source digest:
`d861172b1437057a913c12ef7937a91eef7569deb7dd8ddae19d0d05a8655d59`.
Wheel SHA256:
`9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa`.
Clean installed metadata/stdIO83 tools/27 mutations принят без source PYTHONPATH.
Working v1 сохраняется отдельно. [Контрольная точка dev96](CHECKPOINT_DEV96.md).

## Source и проверки пакета

- Full pure на HEAD `56fbc39608556878745ba1b4d81acb18d774424d`:
  **10149 passed,323 CAD deselected /526,73 с**, normal exit0.
- После этого isolated namespace/window collector на source `402a310`:
  **155 related pure passed /3,77 с**. Package source от installed build Git
  не изменён; full-набор не повторяется после каждого helper.
- B3 source routes I01…I13 и direct metadata/feature/dimension/geometry/component
  observers подготовлены. Actual namespace/PID tables и native window binding
  подготовлены для соединения с SDK. [Source checkpoint](B3_SOURCE_CHECKPOINT_DEV96.md),
  [конкретные native-gates](B3_NATIVE_DRIVER_MAP.md).
- Installed metadata-only B3 preflight13 groups/27 tools, timings enabled/
  disabled/storage-unavailable и public B2 prerequisite-only preflight приняты.
  Они не выполняли actual CAD и не заменяют native acceptance.
- Pure-сценарии используют искусственные native getters/handles. Все323
  deselected CAD-теста исключены явно, не объявлены пройденными.

## Незавершённая приёмка

В момент подготовки пакета один native owner выполняет fresh N5 `child_plane`.
Исходные четыре construction jobs succeeded; `feature.prepare_leaf_deletion`
ещё running. Все30 fixed helpers этого прогона неизменны. Пакетная отправка
не прерывает CAD-вызов и не устанавливает другой wheel.

После terminal result/root audit/own cleanup последовательно выполняются
`unused_equation`, `linked_equation`, затем public B2. B3 actual installed/
internal/public driver, B4 late/restart/reconciliation/native telemetry и B5
сквозной сохраняемый сценарий остаются открытыми. Стадия2 не расширяется.
Импорт/экспорт/STL отложены. [Актуальный аудит](PLAN_STATUS_AUDIT.md).

Обязательный `Checks/unit-and-build` должен реально запуститься на отправленном
head. Старый success38193016491 относится только к9489360 и не засчитывается
новому пакету. Новая CI-сборка сама по себе не имеет native-приёмки текущего
installed wheel. PR остаётся draft; main не обновляется до требуемой приёмки.
CAD-файлы, шаблоны, PDM-данные и полные журналы не публикуются.

## Фактический результат после отправки

Один push выполнен на head `274085fa75cd3d266afe72e55bf0e0175eca8124`.
PR15 остаётся draft. [CI run38451907929](https://github.com/babkin-kd/SolidWorks-MCP/actions/runs/38451907929)
завершился failure: **25 failed,10145 passed,323 deselected /1276,02 с**.
Build/install/metadata этапы skipped. Причина25 отказов — test fixtures во
внешнем pytest temporary directory вместо требуемого private `work/`; локальный
basetemp внутри `work/` скрывал ошибку. Production guards сохраняются, исправление
и проверка с внешним временным каталогом накапливаются локально.

N5 `child_plane` первой попытки завершился failed после пяти нормально
вернувшихся native-операций: canonical binding новой плоскости не подтверждён.
Setup unknown/unresolved сохранён, preview/delete ещё не выполнялись. Независимая
инспекция подтвердила quiescence/собственный scope. Обе собственные детали закрыты;
отдельный read-only аудит подтвердил исходный composite baseline/CIPFalse,
non-STL настройки и неизменный unknown журнал. Ошибка сравнения list/tuple в
maintenance cleanup report сохранена отдельно; CloseDoc не повторялся.
Ни этот случай, ни общий B2 gate не приняты. Запись о running выше описывает
момент подготовки пакета.

Локальное исправление CI test fixtures подтверждено **187 pure passed /77,30 с**
с внешним pytest basetemp. Root связанные binder/baseline/observer/refusal группы:
**42+48+208 passed**. Это485 связанных pure-проверок, не новый full/CI результат.
Production private-path guards сохранены; повторный push не выполнен.

После локального исправления полный source-набор на b842a9c принят:
**10220 passed,323 CAD deselected /462,70 с**, external pytest basetemp,
normal exit0. [Точная локальная контрольная точка](CHECKPOINT_B842A9C.md).
Этот результат не заменяет remote CI failure или текущую native-приёмку.
