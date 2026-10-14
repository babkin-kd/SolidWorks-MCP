# Короткая native-проба setup B3

`scripts/verify_b3_part_setup_probe.py` подготовлен для единственного
COM-владельца после завершения текущего B2 и подтверждённой собственной
очистки. Не запускать параллельно с N5, v1 или другим CAD-драйвером.
Цель — проверить фактическую совместимость source setup и maintenance,
до длительного SDK/13-групп прогона. Это не B3/native acceptance.

До подключения к CAD требуются `--run-solidworks`, новый private каталог
в `work/`, явный абсолютный существующий `.prtdot`, exact wheel/version/build
и уже принятый metadata-only report этого wheel. Повторный SDK/server не
создаётся. Preflight сверяет установленный пакет без source PYTHONPATH,
metadata и15 helper hashes; реальные файлы и пути остаются private.

Driver вызывает реальный `prepare_part_setup`: основная двухконфигурационная
деталь с двумя solid и sheet, dirty сосед, отдельный Y-cylinder Ø12×30,
original topology44/19. Externally retained receipts и raw NewDocument handles
удерживаются в исходном STA. Полный model/window roster и app/part события
проверяются на каждый admission; имена/пути/roster differences не создают
владение. Private pending/returned журнал сохраняется с fsync.

Нормальный setup выдаёт `probe_complete_guard_held`, `probe_passed=true`,
но `accepted`, `native_acceptance`, `sdk_ready` остаются false. Открыты
whole-session/B1-sketch/assembly/SDK и все13 групп B3. Ошибка, потеря ack или
неполный receipt удерживают исходного владельца без retry/Undo/Save/Close.

После нормального setup root может запросить maintenance в том же живом STA.
В частный `maintenance-request.json` записываются только operation
`close_owned_and_restore_baseline`, точный `owner_pid` и одноразовый
`request_token` из `probe-report.json`. Иной процесс/токен/фаза запрещены.
Не останавливать child и не усыновлять его модели заново по названиям или HWND.

Перед первой записью maintenance проверяет original receipts, три birth
handles/windows, два одинаковых current closed-state снимка, отсутствие
зависимостей/чужих моделей/активного эскиза/AddToDB, настройки и original guard.
Перед каждым CloseDoc и восстановлением guard native event envelope охватывает
pending journal, current roster, target recheck и последний persist. ABA/race
запрещает запись; события предыдущего нормального own CloseDoc принимаются на
следующей opening boundary. Raw return сохраняется до ack, survivors проверяются
после каждого закрытия. Повтор maintenance запрещён даже после отказа.

После пустых original document/window rosters, ActiveDoc=None, нормально
восстановленного own CIP и исходных application context/non-STL prefs остаётся
`maintenance_complete_owner_held`. Затем в исходном STA последовательно
возвращаются application sink.close, adapter.close и CoUninitialize. Только
после всех трёх normal returns публикуются `terminal`, `shutdown_complete=true`
и `retained_process=false`. Отказ удерживает `shutdown_failed_owner_held` с
точным pending шагом; повтор shutdown/maintenance запрещён.
Это maintenance baseline указанной пустой сессии; весь B3 whole-session oracle
и native-приёмка этим не заменяются. STL по-прежнему отложен.

Проверки source: исходный root combined187/1,20 с; после исправления shutdown
root combined **192 pure passed /1,12 с**,
normal exit0, внешний basetemp. Реальная source-оркестрация вызвана с actual
Owner/NativeWatch classes, API-shaped artificial geometry и original raw births;
tests на ABA/journal loss/unknown запрещают повтор и CloseDoc. COM/CAD не
вызывались. Actual template/API/event registration/setup/maintenance пока
**not_run**. Full11104 source39eeb8d не включает этот новый driver/test.

Офлайн AST-аудит установленного generated typelib31 подтвердил все четыре
required DSldWorks app events и сигнатуры шести используемых методов:
planar surface/sheet/imported surface, configuration, circle, CloseDoc.
Исходный typelib SHA256
`0c8551ee5a95082b7a351deb23714c034e0c134e3af84cb73721bac4c40c10cc`.
COM objects не загружались, CAD не подключался. Это availability/signature
evidence, не подтверждение фактического результата, event delivery или setup.

Точный native-кандидат для будущего запуска — прежний installed dev96.
Перед запуском root проверяет final helpers и actual metadata/wheel anew,
не пересобирая/не устанавливая пакет в занятую сессию. Матрица B3 остаётся
[B3_ACCEPTANCE_MAP.md](B3_ACCEPTANCE_MAP.md); этапы проекта не меняются.
