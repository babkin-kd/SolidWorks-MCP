# Отдельный baseline legacy CAD-тестов

Срез 11.10.2026: collection-only обнаружил **323 случая в22 группах**.
Это legacy `SolidWorksSession` исходников, включая общие binding/константы;
это не публичный runtime v2. Предыдущие отчёты `deselected` и `skipped` не
доказывают прохождение CAD. Полный baseline пока **не подтверждён**.
Точный список node IDs сохраняется в частном реестре, не включает CAD-файлы.

| Группа | Случаев | Назначение / необходимые ресурсы | Предыдущие доказательства / приоритет |
| --- | ---: | --- | --- |
| test_features | 137 | Детали/размеры, также экспорт/материалы/views; part template, отдельные material files | Полный набор не подтверждён;20 простых случаев выбраны для пилота |
| test_documents | 4 | Документы/сборки/refs; part и assembly templates | Не подтверждено; отдельная многодокументная оболочка требуется |
| test_guard | 1 | CommandInProgress | Не подтверждено, отдельный guard oracle |
| test_bodies | 7 | Многотельные детали | Не подтверждено; после пилота по необходимости |
| test_corner_radii | 10 | Радиусы профилей | Не подтверждено; по изменениям legacy |
| test_edges | 7 | Рёбра/геометрия | Не подтверждено; по изменениям binding |
| test_equations | 7 | Уравнения/размеры | Не подтверждено; приоритет после размеров |
| test_history | 10 | История/удаление/подавление | Не подтверждено; отдельный аудит владения |
| test_sketching | 9 | Эскизы/отношения | Не подтверждено; приоритет после размеров |
| test_assembly | 40 | Сборки/mates, saved component fixtures | 40 прежних skipped не являются приёмкой; assembly template |
| test_drawing | 5 | Чертежи | Не подтверждено; drawing template |
| test_import | 8 | Импорт/экспорт | Не подтверждено; отложено |
| test_joints | 15 | Соединения/геометрия деталей | Не подтверждено; по инженерной потребности |
| test_mirror | 7 | Зеркальные операции | Не подтверждено; по инженерной потребности |
| test_moulded | 5 | Формованные детали | Не подтверждено; будущая область |
| test_person_part | 11 | Составные сценарии детали | Не подтверждено; после базового baseline |
| test_placement | 6 | Размещение/координаты | Не подтверждено; по инженерной потребности |
| test_printability | 6 | Печать/сетки | Не подтверждено; отложено |
| test_selftest | 2 | Диагностика среды/шаблонов | Не подтверждено; отдельные разрешения CAD-оболочки |
| test_shape_tools | 17 | Геометрические вспомогательные операции | Не подтверждено; по инженерной потребности |
| test_sheet_metal | 5 | Legacy листовой металл | Не подтверждено; не переносить v2 sheet receipts |
| test_text | 4 | Текст/шрифты | Не подтверждено; установленные шрифты |

Все группы требуют Windows/запущенный SolidWorks и доступную базовую CAD
лицензию. PDM/Simulation/Routing этот набор не проверяет. Точные необходимые
шаблоны читаются из установленной среды; реальные пути не публикуются.
Длительности групп пока не измерены. Статус отдельного случая хранится как
passed/failed/skipped/not_run/unknown, а не выводится из размера группы.

## Оболочка и пилот

Оболочка включается только `--legacy-cad-pilot-report`; обычные legacy fixtures
пока сохраняют прежнюю очистку и не объявлены безопасными для полного набора.
Один synchronous процесс, одна пустая сессия, явный `--run-solidworks`.
Для каждого part-case захватывается точный native IUnknown сразу после создания;
перед закрытием проверяются единственный документ, identity, текущая ревизия
и blocking0. Фактический пустой roster обязателен: exception и no-op CloseDoc
не подавляются. Чужой/лишний/blocked документ сохраняется, `--maxfail=1`
останавливает новые случаи. Собственный CommandInProgress восстанавливается
с readback; final roster/visible/non-STL preferences проверяются независимо.
STL явно вне scope, изменения его настроек записываются отдельно.
Контрольные модели/отчёты остаются в ignored work/, пользовательская v1 не меняется.

Перед20-case пилотом выполняется отдельный native cleanup-probe одного простого
box-case. Runner разрешает пилот только при accepted probe с теми же hash
оболочки и digest legacy исходников. Pure failure-oracles проверяют отказ
закрытия, no-op, чужой/blocked roster; они не являются native-доказательством.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='src'
.venv/Scripts/python.exe scripts/run_legacy_cad_pilot.py --mode inventory --state-dir work/legacy-inventory-fresh
.venv/Scripts/python.exe scripts/run_legacy_cad_pilot.py --mode cleanup-probe --run-solidworks --state-dir work/legacy-cleanup-fresh
.venv/Scripts/python.exe scripts/run_legacy_cad_pilot.py --mode pilot --run-solidworks --cleanup-report work/legacy-cleanup-fresh/report.json --state-dir work/legacy-pilot-fresh
```

Каждый state-dir должен быть новым; повтор результата не подменяет предыдущий.
20 node IDs зафиксированы в runner: box/cylinder/cone/disc/revolve, signed и
angular dimensions, отказы negative/zero/equation-driven, параметрические
размеры профиля, global variable и face/edge census. Новые формы, импорт/STL,
сборки, чертежи и их многодокументная cleanup не входят в пилот.
Существующие legacy имена элементов сохранены ради тестируемого контракта;
этот набор не доказывает русскую naming policy v2.

## Фактический пилот 11.10.2026

**Пилот принят в своей legacy-области:**20 passed/0 failed/0 skipped/0 not_run,
unknown=false. Предварительная native cleanup-probe:1 passed,3,11с pytest/
3,31с полное выполнение,0,14с очистка. Пилот:54,27с pytest/54,47с полное
выполнение;2,996с на20 очисток (в среднем0,150с). Время cleanup уже входит
в общее, его не прибавлять повторно. Диагностика/восстановление не требовались.
Затраты этого конкретного пилота не экстраполируются на сложные группы.

| Привязка | Значение |
| --- | --- |
| Git исходников и оболочки | `95f0e58af9a6bf08a63eb46c58af5c47f0a6119c` |
| Версия legacy исходников | `2.0.0.dev78` |
| Source digest | `63ca5dafabf245da0365cd948791b0a4897dd4f15453973c4ef4379eefb66fb2` |
| Cleanup-probe report SHA256 | `661270c964cad5997189b20e73f27934f59ee87db1e938a1ec01b622c31a6492` |
| Pilot report SHA256 | `6dc18c39f69137bd571dc4b9d0ef7921a0062f93e2cea8109b4ac8a3d7b76c01` |
| CAD | SolidWorks31.2.1 |

Все20 owned identities закрыты с native readback; roster пустой,
CommandInProgress=False, visible восстановлен, изменённых preferences нет.
STL не засчитывается как отдельная приёмка даже при совпавшем снимке.
Source запуск с PYTHONPATH=src — **не installed wheel/native v2 acceptance**.
Полный baseline открыт:20 из323 cases приняты, остальные303 not_run в этом
пилоте; их прежние доказательства остаются «не подтверждено».

Следующие группы выбирать по изменениям зависимостей и инженерной потребности:
эскизы/уравнения/история после расширения безопасного владения их fixtures.
До запуска test_documents/assembly/drawing требуется отдельный exact-owned
многодокументный teardown; старая `_close_documents` ещё подавляет ошибки.
Ежедневный полный323-run не вводится. Mandatory v2 gates остаются в матрице.
