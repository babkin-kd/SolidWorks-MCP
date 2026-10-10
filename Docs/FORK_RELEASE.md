# Выпуск кандидата нашего форка

Наш форк: `babkin-kd/SolidWorks-MCP`. Upstream-лицензия и атрибуция сохраняются. Рабочая v1 и её локальные правки остаются в отдельном окружении.

## Что проверяет CI

Проверка `unit-and-build` сохраняет своё имя и запускается для PR в `main`, push в `main` и явного `workflow_dispatch`. Фильтры путей и пропуск обязательных проверок не добавлены. Job выполняется только в нашем форке, с `contents: read`.

1. `uv lock --check` проверяет соответствие зависимостей проекту; следующие операции используют `--frozen`.
2. Pure-тесты идут на Python 3.12 с фильтром `not solidworks`. Они не заменяют native CAD/PDM/Simulation-приёмку.
3. Генерируются build metadata с Git SHA, признаком чистоты исходников, версией API и digest Python/guide-файлов. Собираются wheel и sdist.
4. Runtime-зависимости экспортируются из lockfile; wheel устанавливается в отдельный `work/wheel-smoke`, без editable-установки проекта.
5. `verify_installed_metadata.py` проверяет архив wheel, расположение установленного пакета в `site-packages`, entry point, идентичность build metadata и настоящий MCP stdio. Вызываются только initialize, tools/list и system_get_info; CAD/job-инструменты не вызываются.

Метаданные каталога должны соответствовать реализованным инструментам, схемам и revision scopes. Статический список 18 инструментов относится к нынешнему контракту v2 и изменяется вместе с реализацией/приёмкой новых публичных команд. Неподтверждённые PDM/Simulation или legacy aliases не включаются в каталог.

## Артефакты и публикация

Только успешный **ручной** запуск сохраняет wheel, sdist и обезличенный metadata-отчёт в GitHub Actions Artifacts. Автоматической публикации в PyPI, MCP Registry или GitHub Releases нет. Создание артефакта не является завершением стадии или native-приёмкой. CI не получает приватные модели, шаблоны, PDM-данные и журналы из `work/`.

Корневой `server.json` удалён из активного контура. [registry-server.template.json](registry-server.template.json) — справочный шаблон с собственным namespace форка и незаполненным `__FORK_PYPI_PACKAGE__`. Он не объявляет существующий публичный пакет. Перед отдельной публикацией требуется выбрать доступное собственное имя дистрибутива, настроить v2 console command и обязательный приватный `--state-dir`, проверить актуальную registry schema и ownership, согласовать точный выпуск после native-приёмки. В README пока отсутствует активный `mcp-name` marker; PyPI-ссылка upstream подписана отдельно.

## Локальная проверка готового wheel

```powershell
$env:PYTHONPATH = $null
.\work\wheel-smoke\Scripts\python.exe scripts\verify_installed_metadata.py `
  --wheel <точный-wheel> --expected-version <версия> --expected-git-sha <полный-SHA> `
  --state-dir work\metadata-новый-запуск --report work\metadata-новый-отчёт.json
```

В качестве Python использовать окружение, в котором установлен указанный wheel. Для каждого прогона нужны новые state/report paths; предыдущие доказательства не перезаписываются. Новый wheel устанавливается в dev/контрольное окружение, рабочая v1 не заменяется.

Offline `verify_wheel_artifact.py` не исполняет код архива. Проверяет fork repository URL, единственный v2 entry point и его модуль, согласованные версии, чистый полный Git SHA, digest, отсутствие неожиданных пакетов, CAD/журналов и некорректных ZIP-путей. Это проверка целостности ожидаемого артефакта, а не криптографическая аттестация издателя или CAD-приёмка.

## Подтверждённый локальный результат

На отдельном окружении Python 3.12.14 проверен ранее принятый dev27 wheel из `8cf1e42226bc17e5975c5570cadf3dd1046f2422`, SHA-256 `ec7eae97e4c809d2f52022dcc34380161b6588a13a279815691710204a9394d9`. Из lockfile установлены MCP 1.30.0/pywin32 312 и остальные точные runtime-зависимости; SDK, схемы 18 инструментов и source digest совпали. CAD/job-инструменты не вызывались, `native_acceptance=false`.

В том же отдельном locked-окружении: **2046 pure passed, 321 CAD deselected**; 50 целевых artifact/metadata/packaging тестов passed. Actionlint 1.7.12 и PowerShell Parser приняли workflow. Это локальная проверка нового контура на историческом принятом wheel, не проверка новой сборки из текущего HEAD и не GitHub Actions run. Push, workflow dispatch и публикация не выполнялись. Контрольные документы после прерванного legacy-прогона закрыты по прямому запросу пользователя без сохранения, файлы не изменились и открытых документов нет. Служебный флаг сохранён, его сброс и новый native baseline ещё требуют согласования; стадии 1–3 ещё не завершены.
Дополнительно проверен новый чистый dev27 wheel из `34bc3ff26f4d715cff802e6846cd64209beb7063`, SHA-256 `92fd14f204007ffb77531d2c18668f3eeae3de3bc07fa4430f31bb18a7b9a1c1`: отдельная locked-установка, настоящий stdio и 18 схем совпали, CAD/job-вызовов не было. Это metadata-only acceptance этой точной сборки, не native acceptance и не проверка последующего dev28 исправления импорта.
