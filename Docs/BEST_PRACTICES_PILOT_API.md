# Native equation API для пилота лучших практик

Дата доступа: 2026-10-11. Цель: проект BP-05 стадии 2 с одной конфигурацией
детали и предполагаемым графом `X2 = W - X1`, `Y2 = Y1`, `D2 = D1`.
Это записка о документированном контракте восьми API, а не отчёт о CAD-приёмке.
Страницы не входят в корпус инженерных источников и JSON-карточки практик.

Полный предметный текст прочитан через браузер/UI: обычный web open возвращал
JS-оболочку. Скрытый in-app browser был недоступен при этой проверке; использован
Chrome с отдельной временной вкладкой. Пользовательские вкладки не изменялись.

## Прочитанные источники

Издатель всех восьми страниц: Dassault Systèmes SOLIDWORKS. Заголовок редакции:
`SOLIDWORKS API Help 2023`; footer: `API Help 2023 SP05`, copyright 1995–2026.
Дата публикации отдельных страниц не установлена. URL ниже — фактические адреса
прочитанных страниц, включая различие регистра в пути Add3.

| API | URL | Прочитанные локаторы | Availability |
| --- | --- | --- | --- |
| Add2 | [Add2 Method (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Add2.html) | .NET Syntax; Parameters; Return Value; Remarks; Availability | SOLIDWORKS 2010 FCS, Revision 18.0 |
| Add3 | [Add3 Method (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IEquationMgr~Add3.html) | .NET Syntax; Parameters; Return Value; Remarks; Availability | SOLIDWORKS 2014 FCS, Revision 22.0 |
| Equation | [Equation Property (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Equation.html) | .NET Syntax; Parameters; Property Value; Remarks; Availability | SOLIDWORKS 2001Plus FCS, Revision 10.0 |
| GetCount | [GetCount Method (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~GetCount.html) | .NET Syntax; Return Value; Availability; Parameters/Remarks отсутствуют | SOLIDWORKS 99, datecode 1999207 |
| Value | [Value Property (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Value.html) | .NET Syntax; Parameters; Property Value; Remarks (пустой); Availability | SOLIDWORKS 2001Plus FCS, Revision 10.0 |
| Status | [Status Property (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Status.html) | .NET Syntax; Property Value; Remarks; Availability; Parameters отсутствует | SOLIDWORKS 2001Plus FCS, Revision 10.0 |
| Disabled | [Disabled Property (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Disabled.html) | .NET Syntax; Parameters; Property Value; Remarks; Availability | SOLIDWORKS 2017 FCS, Revision 25.0 |
| EvaluateAll | [EvaluateAll Method (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~EvaluateAll.html) | .NET Syntax; Return Value; Remarks; Availability; Parameters отсутствует | SOLIDWORKS 2010 FCS, Revision 18.0 |

SP05 отличается от целевой установки SolidWorks 2023 SP2.1. Указание Availability
подтверждает документированную историю появления API; оно не доказывает
работоспособность нашего COM-вызова на SP2.1.

## Add2: создание в одноконфигурационной детали

Документированная сигнатура: `Add2(Index, Equation, Solve) -> Integer`.
`Index` начинается с нуля; `-1` добавляет в конец. `Equation` содержит выражение.
`Solve=true` требует немедленного вычисления, `false` откладывает его.
Возвращается индекс добавленной записи либо `-1` при ошибке.

В Remarks указано: повторная левая часть существующего уравнения вызывает
ошибку. Добавлять запись во время обхода списка уравнений нельзя из-за риска
сбоя SolidWorks. При отложенном вычислении запись появляется в дереве после
`EvaluateAll` или `EditRebuild3`; первый рассмотрен ниже, контракт второго
не исследован. Для моделей с несколькими конфигурациями 2014+ справка направляет
к Add3. [Источник: Add2, Parameters / Return Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Add2.html).

## Add3: ограничение и причина выбора Add2

Сигнатура: `Add3(Index, Equation, Solve, WhichConfigurations, ConfigNames)
-> Integer`. Индекс, строка, флаг вычисления и результат имеют тот же смысл.
`WhichConfigurations` задаётся через `swInConfigurationOpts_e`; `ConfigNames`
используется для `swSpecifyConfiguration` и должен включать текущую
конфигурацию. Численные enum-значения здесь не проверены.

Remarks ограничивает метод деталями с несколькими конфигурациями, созданными
в SolidWorks 2014+. Для одной конфигурации явно рекомендуется Add2, который
не поддерживает выбор конфигураций и описан как немного более быстрый.
Глобальные переменные и component equations требуют `swAllConfiguration`;
изменять запись Add3 следует через `SetEquationAndConfigurationOption`.
Повтор dimension equation допускается только при подавленной существующей
записи, с её последующим включением; повтор global variable assignment даёт
ошибку. [Источник: Add3, Parameters / Return Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IEquationMgr~Add3.html).

**Выбор для проекта одноконфигурационного пилота — Add2.** Расширение на несколько
конфигураций требует отдельного контракта, реализации и native-приёмки.

## Equation: текст для чтения и изменения

`Equation(Index)` — читаемое и записываемое строковое свойство; индекс начинается
с нуля. Его значение — текст уравнения, а не документированный результат
вычисления. В разделе Property Value отсутствует код успеха записи.

Имена размеров и глобальных переменных оформляются кавычками. Remarks всех
трёх страниц объясняет удвоение кавычек при задании строковых литералов в
примерах. Это нельзя механически считать проверенным правилом экранирования
Python/pywin32. Для записи в определённых конфигурациях нескольких конфигураций
указан `SetEquationAndConfigurationOption`; для прямой записи в модель
компонента сборки — предварительный `EditPart2`. Пилот отдельной детали эти
сборочные режимы не включает. [Источник: Equation, .NET Syntax / Parameters / Property Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Equation.html).

## GetCount: границы обхода

`GetCount() -> Integer` не принимает параметров и возвращает число уравнений
модели. Разделов Parameters и Remarks на прочитанной странице нет; специальные
коды ошибок и правила включения отключённых записей в счётчик здесь не
описаны. [Источник: GetCount, .NET Syntax / Return Value](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~GetCount.html).

Для проекта readback это граница индексного обхода, не показатель исправности
выражений. Наш алгоритм должен сначала получить снимок записей без изменений
списка; особенности обхода отключённых записей остаются native-prerequisite.

## Value: численное значение и неопределённые здесь единицы

`Value(Index)` — read-only `Double` для уравнения с нулевым начальным индексом.
Property Value описывает значение либо `-1` при выходе индекса за границы.
Remarks на странице пустой. Единицы длины/угла, перевод в SI, соответствие
единицам документа и момент актуализации значения на этой странице не
определены. [Источник: Value, .NET Syntax / Parameters / Property Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Value.html).

Поэтому нельзя автоматически интерпретировать Value как метры или миллиметры.
Число `-1` также нельзя использовать как единственный тест ошибки любого
выражения: отрицательное число может быть допустимым результатом API в иных
сценариях. В нашем пилоте контролируемые длины положительны. Для проекта
требуется сопоставление границ индекса, непосредственного
Status после чтения, согласованных единиц и независимого readback размера.

## Status: последняя операция, а не индексированный набор статусов

`Status` — read-only `Integer` без параметров. Общее описание и Property Value
говорят о последнем выполненном уравнении: индекс последнего успешно
выполненного, либо `-1` при ошибке. Remarks уточняет последовательность:
после метода или свойства IEquationMgr с индексным аргументом, например
`Value(i)`, последующее чтение Status возвращает `i` при успешном вызове или
`-1` при ошибке. [Источник: Status, .NET Syntax / Property Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Status.html).

Здесь **нет свойства `Status(i)`**. Это состояние последней операции, которое
может смениться при следующем индексном вызове. Для проекта можно сохранять
пары «индексный вызов → немедленно Status», не вставляя между ними другие вызовы
EquationMgr. Такая пара доказывает документированный успех конкретного вызова;
она не является самостоятельным набором статусов решения всех выражений и
не подтверждает геометрические постусловия. Требование различать успешное
чтение и корректное решение остаётся обязательным для будущей приёмки.

## Disabled: участие записи в зависимостях

`Disabled(Index)` — читаемое/записываемое `Boolean` с индексом от нуля:
`true` отключает уравнение, `false` оставляет его включённым. Remarks
предупреждает, что отключение убирает запись из списка relations и его нельзя
выполнять во время обхода уравнений из-за риска сбоя SolidWorks. Коды ошибок
индекса и влияние отключения на сохранённое численное Value не определены
на этой странице. [Источник: Disabled, .NET Syntax / Parameters / Property Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Disabled.html).

Для будущего пилота readback текста должен сопровождаться проверкой, что
требуемая связь не отключена. Наличие правильной строки в файле само по себе
не подтверждает участие выражения в вычислении. Отключение пользовательских
уравнений не входит в проект пилота и не служит автоматическим исправлением.

## EvaluateAll: возврат не различает успех и отказ

`EvaluateAll() -> Integer` не принимает параметров. Return Value прямо указывает
`-1` при успехе **и** при неудаче. Remarks рекомендует метод для уравнений,
добавленных Add2/Add3 с `Solve=false`. [Источник: EvaluateAll, .NET Syntax / Return Value / Remarks](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~EvaluateAll.html).

По этому контракту успешный COM ACK или полученный `-1` нельзя считать
успехом всех выражений; дополнительный Status последней операции также не
заменяет проверку каждой требуемой зависимости и геометрии. Это вывод для
нашего исполнительного контура, а не утверждение о проверенном запуске.

## Проектная оценка и открытые prerequisites

Граф `X2=W-X1`, `Y2=Y1`, `D2=D1` — наша проектная интерпретация, не пример из
прочитанных страниц. До исполнения нужны фактические native-имена размеров,
согласованная единица длины и проверка существующих владельцев левых частей.
Добавление и обход списка должны быть раздельными операциями. Индекс успешного
Add2 и обратное чтение текста — промежуточные факты; они не доказывают
зависимость, отсутствие ошибок или постусловия геометрии.

Открытые prerequisites BP-05:

- Проверить marshalling Add2, GetCount, EvaluateAll, Status и индексированных
  Equation/Value/Disabled через pywin32 на целевом COM-интерфейсе; синтаксис
  из .NET/VBA не считать Python-доказательством.
- Сверить оставшиеся контракты порядка решения и автоматического перестроения,
  а при расширении сценария — конфигураций и подавления. Они не исследованы здесь.
- Сверка GetEquationMgr/EditRebuild3/ForceRebuild3 вынесена в
  [отдельную записку](BEST_PRACTICES_PILOT_REBUILD.md). Поддержанный полноценный
  readback размеров, связей и геометрии нового scope ещё не принят.
  EvaluateAll не предоставляет признака общего
  успеха; прочитанные страницы не определяют единицы Value.
- Установить и подтвердить единицы и актуальность Value сопоставлением с
  независимым размером; проверить ошибку индекса, ошибку выражения и отключённую
  связь на собственных контрольных документах. Отдельный сценарий допустимых
  отрицательных выражений в bounded-пилот положительных длин не добавляется.
- Подтвердить порядок «индексное чтение → Status», поведение GetCount/индексов
  при отключённых записях и диагностирование частичного отказа EvaluateAll;
  одно успешное чтение или отсутствие COM-исключения не засчитывать всей модели.
- Подтвердить сохранение выражений и повторное разрешение ссылок после открытия,
  а затем изменение W без клиентского пересчёта X2 на точном установленном wheel.
- Принять bounded-отказы, scoped restoration и reconciliation для неизвестного
  исхода в рамках существующего контракта ревизии и request_id.

Статус: предметные источники прочитаны; проектный выбор Add2 обоснован.
Реализация, pywin32, установленный wheel, CAD-постусловия и публичная MCP-цепочка
не проверялись. Эта записка не объявляет новый инструмент в API v2.
