# Локальная source-контрольная точка 4ec13fb

14.10.2026, stage-1-fixes. Один итоговый full pure завершился normal exit0:
**11271 passed, 323 CAD deselected /477,04 с**. Исполняемые source/tests не
менялись в прогоне; внешний свежий basetemp, cacheprovider отключён.
Обычные последующие изменения документации не требуют повторения этого набора.

Кандидат включает пакет [0ec9ab9](CHECKPOINT_0EC9AB9.md) и Python-only
dimension-read диагностику B2 collector/wrapper. Она сохраняет role/boundary/
stage/known anchors и исходное исключение, без новых COM getters после отказа,
без изменения owner/PID admission и без cleanup/acceptance authority.
Root integration148 pure/38,73 с отдельно проверила actual artificial registry/
JobRunner/SQLite и отсутствие refusal/cleanup после возвращённого отказа.

Installed dev96 по-прежнему build f80ee6d80819140a8122fcf26104b0ce6760bff8,
wheel SHA2569088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa,
metadata83/27. Production src/pyproject.toml не менялись, wheel не
пересобирался/не переустанавливался; v1 сохраняется отдельно.

N5 child-plane-4 failed с returned dimension-owner mismatch, historical
unknown/unresolved сохранён. Independent inspection/close2 controls/baseline
подтверждены. Короткие probes mismatch не воспроизвели; checks не ослаблены.
Fresh child-plane-5 начат с новой диагностикой, отдельным private journal и
32 frozen helpers. Native результат pending; source full его не принимает.
[Доказательства и границы](B2_DIMENSION_OWNER_DIAGNOSTIC.md).

Этот кандидат готовится к одной пакетной отправке. PR15 остаётся draft:
B2/public/N5, B3 actual SDK/13 groups, B4 native и B5 остаются открытыми.
Новый CI должен проверяться по фактическому pushed head; старый green771befa
не переносится на новый пакет. Merge/main/release не выполняются.
