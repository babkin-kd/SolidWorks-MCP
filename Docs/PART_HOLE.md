# Сквозное круглое отверстие: исходная подготовка

## Состояние

Инженерный блок ещё не завершён. Исходный кандидат **dev53** теперь содержит полный circle reader/classifier, домен с durable протоколом, native through-all writer/restore и два MCP-фасада: `part_prepare_through_hole`, `part_create_through_hole`. Исходный каталог — 32 tools/9 mutations. **Installed/native-приёмка отверстия ещё не выполнена.** Установка dev52 и её принятая цепочка вращения сохраняются до установки итогового кандидата; их приёмка не засчитывается за отверстие.

Следующая цепочка: новая деталь → параметрическая пластина → одно сквозное круглое отверстие. Это пункты 1.4 и 2.1 PLAN.md; импорт/экспорт в блок не входят.

## Реализовано в исходниках

`ThroughHole.validate` требует opaque ссылки на исходный эскиз и его плоскость, положительные координаты центра и диаметр в мм. Каждая длина — конечное число от 0,001 до 10 000 000 мм; bool, строки, NaN и infinity отклоняются до native-доступа. Вокруг полной окружности должно остаться минимум 0,001 мм материала до каждой из четырёх сторон исходного прямоугольного основания. Имена по умолчанию: «Эскиз отверстия» и «Сквозное отверстие»; новые имена проверяются как русские и различающиеся.

Ожидаемая форма задаётся в полном model-space через подтверждённый rigid frame исходной плоскости: восемь исходных вершин, двенадцать прямых и два замкнутых круговых ребра, шесть плоских граней и одна внутренняя цилиндрическая стенка. Независимые расчёты: объём `(W × H − πR²) × D`, площадь `2 × (W × H − πR²) + 2 × (W + H) × D + 2πRD`.

`hole_body_matches` сопоставляет полную, уже проверенную читателем native-границу с конкретной формой: все исходные вершины и пары конечных рёбер, шесть внешних плоскостей и их контуры, два центра окружностей, радиус, ось и положение стенки. Совпадение census или массы недостаточно. Функция не заменяет native BREP-reader.

Читатель `planar_body_cylindrical_through_holes_brep_v1` сохраняет настоящие плоскости, цилиндры, line/circle parameters, trim intervals/senses, native tolerances и полные ordered loops/coedges. Проверяет владельцев, взаимных партнёров, winding, связность границы, manifold fans конечных вершин, принадлежность окружностей cap-граням и стенкам, отсутствие пересечения/касания контуров, native Check3 до/после и неизменность root/interior census. Native null для массива вершин периодического контура допустим только при точном zero count. Closing update stamp обязан оставаться native int: равные по значению bool/float не принимаются.

Числа сохраняются IEEE754 hex без округления. Допуск геометрического согласования `1e-12 м` служит для отказа при противоречии и не подменяется reported native gap. Состав геометрии, identity comparisons и геометрические сравнения ограничены бюджетами. Читатель допускает несколько отдельных полных отверстий; первый инструмент создания планируется только для одного отверстия в одном прямоугольном основании.

За пределами этой области: blind/наклонные отверстия, цилиндрические швы, частичные дуги, mixed line/arc loops, cones, торы, скругления, зенковки, резьбы и произвольные Hole Wizard-элементы. Для них нужны отдельные полные области чтения и проверки.

## Проверки и пределы — 10.10.2026

Для полного исходного кандидата dev53: **2875 pure passed, 323 CAD deselected**. До исправления версии справочного Registry-шаблона первый полный прогон дал 2874 passed/1 failed; исправленный итоговый набор прошёл полностью. Это не native-приёмка. Связанные circle/linear/adapter/constraint проверки — 222 passed; domain/MCP/metadata/verifier gates отдельно проверены. Registry-шаблон остаётся справочным, публикация не выполнялась.

`CircularSketchReader` сохраняет полный circle curve, собственный центр/возможные полные seam endpoints, radius/normal/rotation, все relations/definition entities и dimensions. `circle_profile_parameters` выделяет ровно один circle без seam points и три независимых driving dimensions X/Y/диаметра по Type2 и точным native entities, не по именам. Для этой операции сохранены binder/reference, plane/origin proof и существующий linear reader. В типовой библиотеке SW2023 подтверждено: `ISketchArc.IsCircle` возвращает LONG; BOOL/truthiness не подменяют этот контракт. Фактические значения вновь созданного круга и его constraints ещё должны пройти installed/native-проверку.

Native и доменные вырезы используют общий путь удержания собственных handles, checkpoint, выделения, through-all Cut4, rebuild, evidence и scoped restoration. Угловой вырез сохраняет свой профиль и scope; круговой — собственные размеры/shape proof и `single_base_circular_through_hole_v1`. Аналитический dispatcher выбирает hole-reader для census 8/14/7, но только полный reader доказывает форму. Полностью плоская репрезентация не менялась; набор с цилиндром/одним отверстием имеет scope `planar_cylinder_or_single_hole_body_set_v1`.

На предыдущем checkpoint `8919902` связанный pure-набор дал **422 passed**: BREP/domain, planar/cylinder, corner-cut preparation и revolve domain. Это искусственные сценарии; тогда полный набор ещё не запускался. Текущий полный результат dev53 указан выше.

Фактический API-пробник использовал временные тела в памяти ядра SolidWorks 2023: `CreateBodyFromBox`, `CreateBodyFromCyl`, `IBody2.Operations2` cut. Он не создавал/редактировал/сохранял CAD-документы и не запускал MCP-мутацию. Две пары полных снимков совпали точно:

| Временное тело | Вершины / рёбра / грани | Native объём, мм³ | Native площадь, мм² |
| --- | --- | --- | --- |
| Пластина 40 × 20 × 10, отверстие Ø6 в (10; 10) | 8 / 14 / 7 | 7717,25666117692 | 2931,9468914507715 |
| Та же пластина, два Ø6 в (10; 10) и (30; 10), тело перенесено | 8 / 16 / 8 | 7434,513322353837 | 3063,893782901542 |

Пустая сессия и `CommandInProgress=False` сохранены; процесс завершён, CAD-документов пробника нет. `CreateBodyFromBox3` в фактической Automation-сессии вернул member-not-found; для временной диагностики использован прежний `CreateBodyFromBox`. Это не новая объявленная серверная возможность.

Ignored evidence: `work/hole-reader-source-probe.json`, `work/hole-reader-source-probe.log`, `work/hole-prerequisites-pure-2.log`. Source SHA256 читателя в пробнике: `376c9bc705b5186b880432541068de2b63de64e81b991227abbd0a217eb27e90`. Затем отдельно усилен closing stamp type и добавлены pure-регрессии; они не выдаются за повторную native-проверку того же артефакта. Пробник **не является installed-wheel/native-приёмкой создания отверстия**.

## До завершения блока

1. Проверить реализованный circle sketch/три независимых размера на фактически созданном круге установленного кандидата; подтвердить его native curve/relations/definitions и точные plane/origin references.
2. Подтвердить фактический through-all cut, собственные handles, русские имена, rebuild, полный BREP/constraint/body proof и независимые mass facts. Доказать scoped restoration cut/sketch; unknown не повторять автоматически.
3. Собрать чистый wheel исходного кандидата с готовыми domain/MCP-фасадами и прошедшим полным pure-набором, установить только в dev-окружение, выполнить metadata и native-приёмку точного пакета без PYTHONPATH исходников.
4. Internal native: stale до записи и восстановление после фактического создания. Public MCP: новая деталь → пластина → отверстие, журнал/постусловия и повтор request_id без второго отверстия. Закрыть свои модели после завершения COM и проверки владения.

Подготовлены `scripts/verify_part_hole.py` и `verify_part_hole_mcp.py`: own fixtures/cleanup gate, same-wheel preflight, internal stale/known restoration и public chain/request_id. AST-контракт проверяет покрытие SDK-вызовов ToolSpecs, полные engineering V/A/census и точные document-create mappings до запуска CAD. Пропуски не засчитываются за пройденные сценарии.

Стадии открыты. V1 и прежний wheel dev52 сохранены; push/Actions не запускались.

## API-источники для следующего шага

- [ISketchArc members](https://help.solidworks.com/2019/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISketchArc_members.html): centre/radius/normal/rotation и различение полного круга и дуги.
- [Типы entities в sketch relations](https://help.solidworks.com/2022/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swSketchRelationEntityTypes_e.html): point=2, line=3, arc=4; отдельный enum от `ISketchSegment`.
- [ISketchRelation.GetEntitiesType](https://help.solidworks.com/2024/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISketchRelation~GetEntitiesType.html) и [ISketchSegment.GetCurve](https://help.solidworks.com/2017/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.isketchsegment~getcurve.html).
- [ISketchArc.IsCircle](https://help.solidworks.com/2022/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISketchArc~IsCircle.html): native integer 1/0.
- [Типы размеров](https://help.solidworks.com/2024/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swDimensionType_e.html?id=2.10.1.272): horizontal=11, vertical=12, diameter=6.

Документация/generated wrapper не заменяют подтверждение native-return semantics установленной версии.
