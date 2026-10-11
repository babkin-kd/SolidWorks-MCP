# Native equation API для пилота лучших практик

Дата доступа: 2026-10-11. Цель: проект BP-05 стадии 2 с одной конфигурацией
детали и предполагаемым графом `X2 = W - X1`, `Y2 = Y1`, `D2 = D1`.
Это записка о документированном контракте трёх API, а не отчёт о CAD-приёмке.
Страницы не входят в корпус инженерных источников и JSON-карточки практик.

Полный предметный текст прочитан через браузер/UI: обычный web open возвращал
JS-оболочку. Скрытый in-app browser был недоступен при этой проверке; использован
Chrome с отдельной временной вкладкой. Пользовательские вкладки не изменялись.

## Прочитанные источники

Издатель всех трёх страниц: Dassault Systèmes SOLIDWORKS. Заголовок редакции:
`SOLIDWORKS API Help 2023`; footer: `API Help 2023 SP05`, copyright 1995–2026.
Дата публикации отдельных страниц не установлена. URL ниже — фактические адреса
прочитанных страниц, включая различие регистра в пути Add3.

| API | URL | Прочитанные локаторы | Availability |
| --- | --- | --- | --- |
| Add2 | [Add2 Method (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Add2.html) | .NET Syntax; Parameters; Return Value; Remarks; Availability | SOLIDWORKS 2010 FCS, Revision 18.0 |
| Add3 | [Add3 Method (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IEquationMgr~Add3.html) | .NET Syntax; Parameters; Return Value; Remarks; Availability | SOLIDWORKS 2014 FCS, Revision 22.0 |
| Equation | [Equation Property (IEquationMgr)](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Equation.html) | .NET Syntax; Parameters; Property Value; Remarks; Availability | SOLIDWORKS 2001Plus FCS, Revision 10.0 |

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
`EvaluateAll` или `EditRebuild3`; контракты этих методов в этой записке не
исследованы. Для моделей с несколькими конфигурациями 2014+ справка направляет
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

## Проектная оценка и открытые prerequisites

Граф `X2=W-X1`, `Y2=Y1`, `D2=D1` — наша проектная интерпретация, не пример из
прочитанных страниц. До исполнения нужны фактические native-имена размеров,
согласованная единица длины и проверка существующих владельцев левых частей.
Добавление и обход списка должны быть раздельными операциями. Индекс успешного
Add2 и обратное чтение текста — промежуточные факты; они не доказывают
зависимость, отсутствие ошибок или постусловия геометрии.

Открытые prerequisites BP-05:

- Проверить marshalling Add2 и индексированного get/set Equation через pywin32
  на целевом COM-интерфейсе; синтаксис из .NET/VBA не считать Python-доказательством.
- Сверить контракты дополнительных API для количества, статуса, вычисленного
  значения, активности и порядка решения уравнений; здесь они не исследованы.
- Сверить поддержанный способ вычисления/перестроения и полноценного readback
  размеров, связей и геометрии. Упоминание EvaluateAll/EditRebuild3 в Remarks
  не заменяет чтение их предметного контракта.
- Подтвердить сохранение выражений и повторное разрешение ссылок после открытия,
  а затем изменение W без клиентского пересчёта X2 на точном установленном wheel.
- Принять bounded-отказы, scoped restoration и reconciliation для неизвестного
  исхода в рамках существующего контракта ревизии и request_id.

Статус: предметные источники прочитаны; проектный выбор Add2 обоснован.
Реализация, pywin32, установленный wheel, CAD-постусловия и публичная MCP-цепочка
не проверялись. Эта записка не объявляет новый инструмент в API v2.
