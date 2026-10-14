# Локальная контрольная точка N5/CI — b842a9c

Проверенный source Git SHA: `b842a9cc3fcbc323455f415d44e31f8b57040554`.
Изменения сохранены локально; push и новый CI не выполнялись.

## Изменение поведения

N5 child-plane fixture связывает normally returned объект через actual
QueryInterface с единственной новой операцией до clear/rebuild. Только exact
E_NOINTERFACE допускает переход от IFeature к IRefPlane; чужой canonical или
неизвестный HRESULT отклоняются. Сохраняется полный исходный ordered census.
Terminal baseline проверяется как полный composite native/physical/window
snapshot с пустыми rosters; отсутствие наблюдения не принимается за пустую
сессию. После синхронного возврата JobRunner invocation flag снимается независимо
от succeeded/unknown результата; unknown не превращается в success.

Четыре CI test-fixture файла создают private данные внутри repo/work независимо
от pytest basetemp. Production private-path guards сохранены; outside-work
negative случаи проверяются отдельно. Workflow и обязательные проверки не менялись.

## Проверки исходников

- 42 binder/baseline pure passed /0,22 с.
- 48 target +208 observer/refusal pure passed /4,95 и14,66 с.
- Четыре CI fixture файла:187 passed /77,30 с, basetemp вне work.
- **Full pure:10220 passed,323 CAD deselected /462,70 с**, normal exit0;
  pytest basetemp вне work, `-m "not solidworks"`.

Full command: `.venv/Scripts/python.exe -m pytest -m "not solidworks" -q
--basetemp <external-private-temp> -p no:cacheprovider`, с source PYTHONPATH.
Это проверка исходников, не установленного пакета и не фактического CAD.
CAD deselected не засчитываются. Прежний локальный ACL-denied запуск related
тестов не принят; проверенные замещающие группы перечислены выше.

## Native и installed область

Installed кандидат остаётся exact `2.0.0.dev96`, build Git
`f80ee6d80819140a8122fcf26104b0ce6760bff8`, wheel SHA256
`9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa`.
Package source не изменён; отдельная рабочая v1 сохранена.

Первый N5 child-plane failed/unknown сохранён. После независимой quiescence
инспекции две собственные детали закрыты без сохранения; отдельный read-only
аудит подтвердил исходный полный baseline/CIPFalse/non-STL и неизменный журнал.
Fresh child-plane-2 выполняется в новой сессии/журнале на том же installed wheel,
одним COM-владельцем. Все31 frozen helper SHA неизменны. Новая попытка ещё не
принята; unused/linked equation и public B2 остаются not_run.

## GitHub и конечные gates

Remote head остаётся `274085fa75cd3d266afe72e55bf0e0175eca8124`, PR15 draft.
[CI38451907929](https://github.com/babkin-kd/SolidWorks-MCP/actions/runs/38451907929)
сохраняет failure25/passed10145/deselected323; build/install/metadata skipped.
Локальный full не переписывает этот remote результат. Исправление накапливается
до следующей пакетной отправки и обязательного CI.

N5/public B2, actual B3, B4 и сквозной B5 остаются открыты. Стадия1 не завершена,
стадия2 не расширяется; импорт/экспорт/STL отложены.
