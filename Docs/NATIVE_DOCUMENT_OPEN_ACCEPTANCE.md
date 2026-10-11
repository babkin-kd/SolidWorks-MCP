# Приёмка bounded native open dev87

Приёмка ограниченного `native_document_open_resolved_v1` принята:
internal 13/13, 210,07 с; public MCP 11/11, 189,68 с. L2 закрыт в этом scope.
Проверяется один exact installed wheel без `PYTHONPATH` исходников,
SolidWorks 2023 SP2.1 (`31.2.1`). Installed metadata: 71 инструмент /21 мутация,
output schemas/provenance подтверждены. Полный source pure перед wheel:
5560 passed /323 CAD deselected, 77,43 с. CAD deselected не является passed.

## Точная привязка

- Версия: `2.0.0.dev87`.
- Wheel Git: `6437b337b01300a73c3b97a7604c2fb5cad58729`.
- Source digest: `ec4e6a56d215a6d3e37b447cc4125635ebd05e495b3fdc16f940fcd50f97caa2`.
- Wheel: `solidworks_mcp-2.0.0.dev87-py3-none-any.whl`.
- Wheel SHA256: `97d19212f115e34b5fa1ba618f838406396f24e63a24838617c0a3d5aa52d971`.
- Internal report SHA256: `defd61e56f7ef473374127e1ef2dd336cc9250f0c5f91700cbf494df99881ac6`.
- Public report SHA256: `9b73b67e3f2845acac84efc55e8592ba873fb324130b346c23f8a7b0120fbefd`.

| Внешний verifier/helper | SHA256 |
| --- | --- |
| `verify_native_document_open.py` | `f3d202ee93e18db0df7947a594b076319fc618be569bc17308d7d0bc8728da7f` |
| `verify_geometry_reads.py` | `a87bdfc80e1fe2a94b54d26bef56cd92dfd63dffcfd9120d879946f86fb0d4a0` |
| `verify_native_document_save.py` | `daddc53a8f0485cf1268f52be157e7713b460ca210cc226e7215bb873f8130ba` |
| `verify_document_reads.py` | `1625c117c6238b2173e6e30f648d494426d2f1ddcc5c3fb71e8cf5c82b4b64da` |
| `verify_export_operations.py` | `729b37f34521446335ab5b05a82061fb80281296aa21aa492a3d66d404c918ed` |
| `verify_dimension_mcp.py` | `f070f3343bae2b372ed988a4f4335fd726a65a57a5f0ff51c7aee7f612e5e1db` |
| `verifier_lifecycle.py` | `73d44cf0128e66786842d24c77844ee7f0ce7cd69154e36a8b59c0e284d9d934` |
| `verifier_native_open.py` | `9f57df775dda11c144e3aa5c5e8741d613deccc27f387f62f29cecf895a908f3` |
| `verifier_native_open_acceptance.py` | `b3ff1eeabe24e9f2d8a5befb580f9f55d583289ac0a75c9bc12b1ba38463c7d8` |

External verifier/tests/docs фиксируются после сборки отдельным локальным
коммитом. Исполняемый пакет после wheel Git не менялся. Перед public COM gate
пассивно проверяет точное совпадение wheel identity, всех девяти hashes,
13 internal labels, accepted/terminal/cleanup/baseline. Старый отчёт не подходит
после изменения verifier. Приватные модели, пути и SQLite остаются в ignored work/.

## Пользовательский результат и доказательства

Пользователь открывает точный prepared native-файл и конфигурацию, получает
root/new/borrowed IDs и подтверждённый resolved reference graph.
Поддержаны part, saved resolved assembly и обычный drawing в существующем
контракте. Не добавлены режимы загрузки или новые виды ссылок.

Конечный manifest: 10 shared cases, два только internal failure-protocol cases
и одна итоговая очистка — 13 internal /11 public. Фиксированные labels находятся
в `scripts/verify_native_document_open.py` и проверяются пассивным gate.

- Part «Основная»: два solids/2000 мм³; «Вариант» read-only: один solid/1000 мм³.
  Independent native configuration/body/read-only readback выполнен.
- Assembly с borrowed loaded part, активной в другой конфигурации: actual
  component geometry 1000 мм³; исходная part сохраняет 2000 мм³/«Основная».
  Drawing с borrowed assembly/part и оба new hidden reference closures
  сверяются по точным handles, путям и referenced configurations.
- Dirty сосед сохраняет RAM/геометрию/configuration/references/selection/view,
  файл и окно. Полный original roster/window/application baseline проверяется
  после каждого owned cleanup и в конце, а не только по stamp/bounds.
- Replay возвращает прежний job без второго открытия; loaded source,
  missing configuration и stale revision отказывают до записи.
- CWD, реально изменяемый OpenDoc6, восстанавливается однократно последним
  receipt-bound native-шагом; pending/returned ledger и строгий readback проверены.
- Internal normal null OpenDoc6 получен изменением пути собственного receipt
  на отсутствующий файл. Это fault probe настоящего нормально вернувшегося
  native-вызова, а не приёмка публичного missing-file prepare.
- Второй internal probe бросает Python-ошибку после настоящего normal return:
  закрывается только доказанный own-clean result и baseline восстановлен.
  Throwing COM/pending native проверяются pure; реальный COM throw не заявлен.

В обоих финалах fixtures_closed/baseline_restored/cleanup_confirmed=true,
owned_documents=[]; сессия пустая и свободная, non-STL preferences сохранены.
Jobs internal: succeeded21/failed5, unknown0; public: succeeded20/failed3,
unknown0, шесть committed open. Known failure не считается success.
Две failure-protocol мутации rolled_back, не committed.

## Предыдущие отказы сохранены

- Dev86 internal1 остановился при setup локализованного вида; exact-owned
  четыре фикстуры закрыты, v2 CAD-операции не вызывались. Выбор model-view
  из passive inventory исправлен без повторного CreateDrawView.
- Dev86 internal2: normal returned-new OpenDoc6, но изменённый CWD привёл к
  unknown/hold. После terminal/census own cleanup и исходный CWD восстановлены;
  historical unknown не переписан и запрос не повторён.
- Dev87 internal1: первая операция committed, затем неверный external getter.
  Исправлен на registered `IsOpenedReadOnly`; две own fixtures закрыты.
- Dev87 internal2: семь cases, включая drawing borrowed; external owner
  CloseDoc переключил active на referenced assembly. Whole failed, не accepted.
  Независимый census подтвердил сохранность моделей/окон/файлов/CWD; три свои
  модели закрыты. External cleanup теперь one-shot восстанавливает прежний
  живой active handle и не обращается к retired COM. Четыре fake-регрессии
  добавлены; related 499 passed/1,15 с. Они не являются CAD-приёмкой.

## Граница завершения

L2 закрыт обоими accepted gates этого точного wheel.
Первое сохранение L3, базовые B1–B4 и общий same-wheel сценарий S1-B5 остаются
отдельными блоками. Dirty-owned/retained-reference close, arbitrary load/reference
modes, multi-config mutations и 1000+ — видимые задачи стадии 2.
Гарантии безопасности обязательны во всех поддержанных случаях.

[Контракт](NATIVE_DOCUMENT_OPEN.md), [матрица](STAGE_1_REQUIREMENTS_MATRIX.md),
[приёмка блоков](STAGE_1_BLOCK_ACCEPTANCE.md). Стадия 1 остаётся открытой.
