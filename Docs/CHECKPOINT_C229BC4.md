# Пакетная контрольная точка source c229bc4

Кандидат от 14.10.2026. В пакет входят исправление private-path fixtures CI,
диагностика и native PID/IsSame-привязка возвращённой плоскости для N5,
private stdio/SQLite/namespace bridge B3, исходные anchors и подготовка
контрольных деталей B3. Новых публичных инструментов этот пакет не добавляет.

Четыре последние связанные подготовительные блока B3 завершены в исходниках:
original body/face/edge anchors, empty-template admission и Y-cylinder,
original application admission, единая подготовка частей с удержанием своего
guard. Их интеграционный набор — **720 pure passed /1,41 с**. Использованы
искусственные CAD getters; actual CAD-приёмка B3 остаётся открытой.

## Локальные проверки кандидата

Один полный pure-набор source c229bc4 завершился normal exit0:
**11054 passed,323 CAD deselected /465,28 с**. Использованы `not solidworks`,
внешний pytest basetemp и выключенный cacheprovider. Исполняемые
source/helpers/tests с начала набора не менялись; последующие изменения
относятся только к документации. Предыдущий полный source d974ffc имеет
**10381 passed /323 CAD deselected /464,36 с** и не подменяет новый кандидат.

Exact installed dev96 остаётся прежним: build Git
`f80ee6d80819140a8122fcf26104b0ce6760bff8`, source digest
`d861172b1437057a913c12ef7937a91eef7569deb7dd8ddae19d0d05a8655d59`, wheel SHA256
`9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa`.
Diff package `src/` и `pyproject.toml` от build Git пуст. Установку не меняли;
native-вызовы работают без source PYTHONPATH. Metadata/stdIO83/27 уже принято
на этом артефакте отдельно.

Дополнительный offline preflight подтвердил exact installed identity,
accepted positive/fault отчёты, их фактический SQLite и сохранение historical
unknown/unresolved. Все31 helpers текущего N5 совпали с зафиксированными SHA.
Этот preflight не подключался к SolidWorks и не разрешает очистку live-прогона.

## Фактические native-границы

Dev96 own-leaf positive2 принят2/2, parent4/4,4136,97 с. Faults1 принят5/5,
9137,84 с; historical unknown сохранён. Полные журналы остаются вне Git.
Dev95 positive suppression/return2/2 сохранён отдельно и не принимается за
same-wheel dev96 release.

Третий N5 child-plane выполняется единственным COM-владельцем; terminal
результат ещё не принят. InsertRefPlane нормально вернулся; окончательная
привязка и refusal gate ещё не подтверждены. Исходные sketch/extrusion jobs succeeded, но
результат всей refusal-цепочки нельзя вывести из этих двух jobs. Прежние два
failed/unknown N5 не повторяются и не переписываются. Следующие gates:
unused/linked equation, public B2, actual B3, recovery B4, сквозной B5.
[Конечная очередь B2](B2_DEV96_REMAINING.md) сохраняет поддерживаемые случаи и
критерии. Стадия1 открыта, стадия2 не расширяется, import/export/STL отложены.

## Пакетная отправка

Перед отправкой актуальные main и рабочая ветка получены напрямую через Git.
Main `3ab795ec9d75e8a0055d41554cd439737b8b82f8` входит в локальную историю;
удалённый head `274085fa75cd3d266afe72e55bf0e0175eca8124` — её предок.
PR15 open/draft, merge не выполняется. Пакет готов к одному push после
успешного итогового pure-набора; обязательный `Checks/unit-and-build` сохраняется.
CI-сборка не получает native-приёмку установленного dev96 автоматически.
Текущий CAD-вызов ради отправки пакета не прерывается.
