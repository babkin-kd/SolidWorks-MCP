# Source-контрольная точка исправления B4 child import

14.10.2026, source34ccab5. Один финальный full pure завершился normal exit0:
**11274 passed, 323 CAD deselected /478,61 с**. Исполняемые source/tests
не менялись во время проверки; свежий внешний basetemp, cacheprovider отключён.
CAD deselected не считаются пройденными.

Перед ним root gates/process/recovery subset214 passed/11,72 с выполнен
без PYTHONPATH. Child запускается direct base Python с -S, первым получает
корень реально импортированного parent package и сверяет его в identity.
Отдельный import control показал, что PYTHONPATH не исполняет editable .pth;
positive child проверен с empty editable site и foreign cwd. Если actual
handle уже terminal до ready, ошибка содержит exit code и bounded stderr.
Timeout не отменяет процесс; handle/start/nonce и native_false gates сохранены.

Это исправление source-only synthetic стенда. Native Q/B4/server integration
не принимаются. Production src/pyproject.toml и installed dev96 не изменены,
новый wheel не устанавливался; v1 сохраняется отдельно.

Предыдущий packet745502e CI38491234891 failed: unit11250 passed/21 failed/
4 errors, build/install/metadata skipped. Без child stderr historical root
cause ещё не доказана. Source-механизм импорта воспроизведён и исправлен;
новый обязательный CI должен быть проверен по следующему pushed head.

Пакет отправлен одним push: eaf5e5b4cd5df0e0cae826a1232768151b49ef4b.
Прямой API подтвердил этот head в draft/open PR15. Новый Checks38495337250 /
job115629709085 создан: lock passed, unit tests in_progress; build/install/
metadata pending. Это не итоговый success; старый failed run не перезапускался.

Native child-plane-5 продолжает BASE-preparation на exact dev96 с32 frozen
helpers; B4 source-правки в этот manifest не входят. Старые unknown сохраняются,
N5/public B2 и B3/B4/B5 gates открыты. PR остаётся draft; merge/main/release нет.
