# Листовой L-профиль — рабочий прототип

Состояние на 11.10.2026: создание folded-профиля и проверки геометрии/владения
испытаны из исходников. **Инструменты MCP ещё не подключены; приёмки точного
установленного wheel нет.** Принятый dev60 имеет38 инструментов /12 мутаций,
рабочая v1 сохранена. Этот блок развивает пункт2.2 PLAN.md.

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
через отдельный ICustomBendAllowance Type=2. До рабочего выпуска требуется
окончательно зафиксировать применимость версии API и native-семантику factory.

На SW2023 исследован InsertSheetMetalBaseFlange2. SOLIDWORKS помечает его
устаревшим с2022 и предлагает CreateDefinition/CreateFeature с
IBaseFlangeFeatureData. Совместимость установленного API важнее механической
замены: современный путь нужно оценить отдельно до окончательного контракта.
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

До рабочего выпуска остаются:

1. Доменная mutation с полной revision, explicit request_id/target/checkpoint,
   двумя полными closing captures и постусловиями; MCP-фасад той же операции.
2. Проверка scoped restoration: удалить только доказанный собственный bundle
   при известном сбое и подтвердить весь исходный empty-state. Подготовленный
   adapter deletion ещё не проверен в CAD; unknown не допускает повтор операции.
3. Stale/некорректные входы до записи, request_id без второго профиля,
   сохранение отдельной исходной модели и UI/настроек; восстановление журнала.
4. Один итоговый clean wheel, полный pure-набор, installed metadata, internal
   native и public MCP stdio приёмка на том же артефакте, без source PYTHONPATH.

Отдельные будущие сценарии2.2: другие профили/отбортовки/гибы, native-развёртка,
две конфигурации, многотельный листовой металл, производственный DXF. Эти пункты
не засчитываются за folded-прототип. Импорт/экспорт остаются отложенными,
стадии PLAN.md открыты; GitHub push/CI пока не выполняются.
