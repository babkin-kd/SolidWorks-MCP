# Листовой L-профиль — принятый блок dev61

Состояние на 11.10.2026: приняты доменная операция и два MCP-инструмента,
каталог40 инструментов /13 мутаций. **3284 pure passed /323 CAD deselected;
installed metadata40; internal native6 /public MCP6 passed, оба accepted=true**
на точном установленном wheel dev61 без source PYTHONPATH. Рабочая v1 сохранена.
Принята только указанная подобласть пункта2.2 PLAN.md; все стадии остаются открыты.

## Инженерный сценарий

Пустая активная деталь, одна явная конфигурация и persistent-ссылка на плоскость
в начале координат. Открытый профиль: (0,H) → (0,0) → (W,0), два полностью
определённых native-отрезка, пять определяющих отношений, собственные размеры
«Ширина полки»/«Высота полки». Листовое основание вытягивается на L, толщина t
направлена влево от профиля. Один сгиб90°, внутренний радиус r, наружный r+t.
Обе полки должны иметь прямой участок минимум0,001 мм за наружным радиусом.

K-фактор — обязательное явное число0…1. Контрольный .42 не является
утверждённым производственным значением. Никакого скрытого K=.5. Аргумент .5
в старом native-фабричном вызове относится к коэффициенту relief, а K передаётся
через отдельный ICustomBendAllowance Type=2. Native-семантика factory подтверждена
на установленном SOLIDWORKS2023; другие версии требуют отдельной проверки.

На SW2023 исследован InsertSheetMetalBaseFlange2. SOLIDWORKS помечает его
устаревшим с2022 и предлагает CreateDefinition/CreateFeature с
IBaseFlangeFeatureData. Совместимость установленного API важнее механической
замены: современный путь требует отдельной оценки и приёмки; этот блок использует
проверенный compatibility-вызов на SW2023.
См. [официальные release notes2022](https://help.solidworks.com/2022/english/api/sldworksapi/ReleaseNotes-sldworksapi.html?id=2.1).

## Полное доказательство результата

Native sheet metal сохраняет швы сгиба на обоих торцах. Ожидаются16 вершин,
28 рёбер и14 граней:20 внешних прямых рёбер, четыре шва, четыре конечные дуги,
12 плоских граней, две цилиндрические стенки. Каждый торец разделён на два
прямоугольника полок и кольцевой сектор сгиба. Counts только выбирают reader;
для принятия сопоставляются все вершины, пары/типы рёбер, trim/центры/радиусы
дуг, полный набор циклов граней, ориентации плоскостей и цилиндров.

Кривые оцениваются через IEdge.Evaluate2. Полный reader проверяет native
vertices/edges/faces, обе стороны coedge/partner, отсутствие открытой/невалидной
границы, loop winding, связанность и закрывающие native stamps. Минимальное
эквивалентное тело16/24/10 не подменяет конкретный ожидаемый sheet-metal BREP.

Независимая проверка объёма/площади использует:

```
Ro = r+t
S = t*(W+H-2*Ro) + π/4*(Ro²-r²)
P = 2*(W+H-2*Ro) + 2*t + π/2*(Ro+r)
V = S*L
A = 2*S + P*L
```

Native definitions отдельно подтверждают толщину, внутренний радиус, длину,
направления, отсутствие симметричного утолщения/таблицы/материального override,
тип allowance и точный K. Геометрия folded-тела не доказывает K: при другом
коэффициенте она остаётся такой же. Аналитическая нейтральная длина
W+H−2Ro+π/2*(r+K*t) — лишь прогноз, не результат native-развёртки.

## Владение и имена

Возвращённые sketch/base handles сохраняются до последующих CAD-вызовов.
Состав sheet/base/flat берётся из exact body.GetFeatures; singleton-папки — из
native GetSheetMetalFolder/GetFlatPatternFolder и их полного membership.
SketchBend и служебные узлы FlatPattern подтверждаются exact native absorption
и GetOwnerFeature. CutListFolder должен содержать только собственное тело.
Полный текущий состав дерева и dependencies закрывают проверку: лишний узел,
старый baseline-node или чужая зависимость запрещают изменения bundle.
Имена и tree-diff не дают права на владение.

Типичный набор новых узлов: собственный профиль/основание, SheetMetal,
SketchBend, подавленная FlatPattern, два служебных эскиза, UiBend,
FoldUpDownSketchFolder, CutListFolder, TemplateSheetMetal/TemplateFlatPattern.
Все получают русские имена; driving-параметр длины — «Длина профиля».
Baseline-узлы не переименовываются. Стандартные библиотечные обозначения этот
сценарий не затрагивает.

На SW2023 FoldUpDownSketchFolder даёт PID другого объекта. Для неё используется
явный owned_absorption_v1: retained exact handle, точный FlatPattern-владелец
и полный bounded/acyclic обход его subfeatures. Некорректный PID не используется.
Другие own-features требуют persistent round-trip; status2 принимается только
для реально подавленного own-feature и совпадающей native identity. Это не
изменяет общий resolver и не разрешает клиенту обращаться к такой папке по имени.
Документированные getters:
[ISheetMetalFolder.GetSheetMetals](https://help.solidworks.com/2024/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISheetMetalFolder~GetSheetMetals.html),
[IFlatPatternFolder.GetFlatPatterns](https://help.solidworks.com/2023/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFlatPatternFolder~GetFlatPatterns.html).

## Полученные результаты и границы

Контрольный пример W40/H20/L30/t2/r2 мм, K=.42:
native V3402,743338823081 мм³, A3749,5928947446205 мм². Source-probe2 подтвердил
полную форму/параметры; source-probe3 — дополнительно собственные refs,
dependencies и русские имена. Успешные source-jobs committed, owning guard
released, собственные несохранённые документы закрыты после терминальных вызовов.
После первого несовпадения census unknown-журнал сохранён, выполнен отдельный
terminal read-only аудит и разрешённая очистка; unknown не переобъявлен успехом.

Общий pure3194 passed /323 CAD deselected после изменения reader; затем108
связанных тестов после добавления ownership/naming/evidence. Они не являются
проверкой установленного пакета или всей текущей сборки. Приватные протоколы:
`work/native-sheet-development-probe-{1,2,3}/`,
`work/pure-sheet-development-final.log`.

## Доменная операция, MCP и восстановление

`sheet_prepare_l_profile` требует document_id/configuration/plane_object_id,
leg_x_mm/leg_y_mm/length_mm/thickness_mm/bend_radius_mm и явный k_factor.
`sheet_create_l_profile` дополнительно требует expected_revision и request_id.
Создание не сохраняет файл и не меняет активную конфигурацию. Имена эскиза,
элемента и тела по умолчанию русские. Перед записью подтверждаются пустое тело,
отсутствие sheet/flat template folders и полный исходный snapshot. После записи —
две закрывающие полные capture, исходные узлы, driving-размеры, весь BREP,
native параметры и принадлежащие операции узлы. Счётчики/масса сами по себе
не разрешают принять результат или удалить модель.

После доказанной полной формы известный сбой допускает удаление только своего
bundle. Native DeleteSelection2 с absorbed-флагом удаляет тело и sheet-узлы,
но может оставить разабсорбированный исходный профиль. Второе удаление без
children-флага разрешается лишь после повторной проверки точного CAN/PID,
неизменного полного sketch snapshot, размерных owners, отсутствия тела/чужих
узлов/новых зависимостей и всего baseline. Source-probe4 выявил это поведение и
сохранил unknown-журнал; probe5 доказал успешное восстановление. Первый unknown
не переобъявлен успехом. Частичная или неподтверждённая форма остаётся unknown,
не допускает автоматического повтора или общей очистки дерева.

## Приёмка точного установленного wheel

- Версия: `2.0.0.dev61`; чистый source commit `4482037089f58f94aea21fed29f74975183595e3`.
- Wheel: `solidworks_mcp-2.0.0.dev61-py3-none-any.whl`;
  SHA256 `a6ccbf941dea3890f7d70647bea7fc8d4d27e1c9be18e88e52c6e4909f021ddb`.
- Package source digest: `2e7b0c32e924f3f40e20e3ab8f25be9e196e940d968f67b0e5c45785161f3b38`.
- Pure:3284 passed /323 CAD deselected,37,83с; CAD-исключения не засчитаны.
- Installed metadata:40 инструментов /13 мутаций; native_acceptance=false в этом отдельном smoke.
- Internal native6: две операции создания детали, короткая полка/stale до записи,
  известный сбой с полным restored empty-state, успешный folded L-profile.
- Public MCP6: stale создания документа, создание/сохранение исходника,
  два request_id случая без дублей документа/профиля и публичное создание сгиба.

Оба native-отчёта accepted=true/fixtures_closed=true на одном wheel. Полное тело
16/28/14 и IsSheetMetal=true; V≈3402,74333882308 мм³/A≈3749,59289474462 мм².
Внутренний журнал:3 committed/1 rolled_back; публичный:3 committed, создание
профиля записано ровно один раз. Все задания terminal, новых unknown нет.
Application/model guard released, selection/non-STL preferences сохранены,
свои документы закрыты после терминальных вызовов, исходная модель и пустой/free
baseline подтверждены. Эти результаты не заменяют historical source unknown.

Приватные протоколы вне Git: `work/pure-sheet-dev61.log`,
`work/metadata-dev61-1-report.json`, `work/native-sheet-dev61-1/report.json`,
`work/native-sheet-mcp-dev61-1/report.json`, исходные development-probe1…5.

Отдельные будущие сценарии2.2: другие профили/отбортовки/гибы, native-развёртка,
две конфигурации, многотельный листовой металл, производственный DXF. Эти пункты
не засчитываются за принятый folded-блок. Импорт/экспорт остаются отложенными,
стадии PLAN.md открыты; GitHub push/CI пока не выполняются.

Разработка следующего отдельного блока native-развёртки: [SHEET_FLAT_STATE.md](SHEET_FLAT_STATE.md).
Source-проба не закрывает его приёмку; результаты folded-dev61 выше сохраняют свой scope.
