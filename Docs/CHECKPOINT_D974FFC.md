# Контрольная точка source d974ffc

Кандидат: native bridge returned IRefPlane → exact current feature для
подготовки отказного N5. Публичный API и installed dev96/f80ee6d/wheel
SHA9088e018 не менялись; diff `src/` и `pyproject.toml` от build Git отсутствует.

Related194 pure passed /31,73 с. Пробы2–5 и их исходы/own cleanup описаны в
[B2_PLANE_RETURN_COMPATIBILITY](B2_PLANE_RETURN_COMPATIBILITY.md). Они
подтверждают совместимость диагностического API, не общий B2 gate.

Один полный pure-набор source d974ffc завершился normal exit0: **10381 passed,
323 CAD deselected /464,36 с**. Basetemp вне work, source PYTHONPATH и фильтр
`not solidworks`. Исполняемые source/helpers/tests во время этого прогона
не менялись; изменялась только документация. Это source-проверка, не
installed/native acceptance; исключённые CAD cases не принимаются.

Новый N5 child-plane-3 запущен последовательно после коротких проб и
installed/positive SQL preflight, на неизменном точном wheel. Root остаётся
единственным COM/native owner. Pure-набор выполняется параллельно без CAD;
оба проверяют зафиксированные исходники. Текущая parent phase=fixture_creation,
процесс live, terminal acceptance ещё не получена.31 native helper SHA
фиксируются до первого вызова; менять их во время проверки запрещено.

Старые два N5 failed/unknown jobs и исходные отчёты остаются неизменными.
Нет повтора их запросов или объявленного success. Unused/linked cases,
public B2, B3–B5 и стадия1 открыты. PR15 остаётся draft; push/CI ещё не было.
