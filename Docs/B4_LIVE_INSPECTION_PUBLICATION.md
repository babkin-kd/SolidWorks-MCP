# Публикация inspect исходному процессу — 14.10.2026

Родитель публикует единственную inspect-команду только исходному живому
дочернему процессу профиля `dimension_commands_live` с полученным ready
и открытым SDK. Проверяются исходный Popen, время создания процесса,
nonce, exact candidate, ready identity, launch spec и контрольные суммы helpers.
Подмена процесса с тем же PID и изменение привязок запрещены.

Попытка фиксируется до проверок и публикации. Ошибка сохраняет исходного
владельца в `InstalledChildError.retained_owner`; повторная отправка запрещена.
Atomic publisher сохраняет partial при ошибке write/fsync/rename и не
перезаписывает существующую команду. Это подготовка B4, без CAD-действий.

Связанные source-тесты launcher и нового набора: **169 passed /3,05 с**.
Новый набор отдельно: **34 passed /1,34 с**. Проверены отказы состояния SDK,
EOF/exit/profile, drift identity/spec/helpers и ошибки физической публикации.
Process в этих тестах искусственный; actual COM/native не выполнялся.

Fresh installed metadata attempt12 exact dev97 прошёл: terminal, исходный
child exit0, SDK83, metadata/profile/control/inspection/host gates true,
полный journal пуст. CAD/job calls отсутствуют. Installed wheel сохранён:
build `49b899c9c6048c89be81e20c9c5c29f0e4ee50d4`, SHA256
`702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b`.
Source PYTHONPATH исключён. Частные отчёты остаются в ignored work/.

Native Q, actual mutation/stop/restart/reconciliation не проверены этим блоком;
B4 и стадия1 остаются открыты. Текущий B2 native owner и frozen helpers не
изменялись. Это третий связанный локальный блок после опубликованного0ea40eb;
CI того коммита не проверяет последующие изменения. Нового push пока нет.
