# Базовый инженерный сценарий детали v2

## Отдельные стадии B1 — исходный кандидат 12.10.2026

Текущий source-кандидат dev90 включает executor/checkpoint/native-step
журнал и условное восстановление доказанного собственного эффекта. Устойчивые
result IDs и runtime/MCP-фасады подключены; нужна native-приёмка.
Dev90 установлен, metadata/stdio79/25 принят; L3 прежнего dev89 принят
[отдельно](NATIVE_FIRST_SAVE_DEV89_ACCEPTANCE.md).
[Точная контрольная точка dev90](CHECKPOINT_DEV90.md).
Ниже сохранены исходные шаги разработки; их pure-результаты не суммируются.

Подключены четыре отдельные инструмента: `sketch_prepare_rectangle`,
`sketch_create_rectangle`, `part_prepare_rectangle_extrusion`,
`part_extrude_rectangle`. После full post-release proof реальный FeatureCatalog
регистрирует exact returned feature, сверяет PID с независимым native anchor
и повторно проверяет supported сессию. Ошибка привязки удерживает unknown
без inverse/retry. Усилены точные plane/frame, dependency/external inventories,
аннотации и полный anchor delta. Только объявленная plane/origin→sketch связь
поддерживается; служебные folder nodes не получают вымышленных PID.
Related294 source pure passed13,28 с: MCP validation/routing, actual durable
JobStore/coordinator и artificial SDK. `work/pytest-rectangle-facades-final-2.log`.
Каталог установленного dev90 подтверждён79/25.

Final source pure: **6390 passed, 323 CAD deselected, 139,96 с**;
`work/pytest-dev90-full-2.log`. Первый полный прогон6389/1 failed (127,63 с)
выявил только несинхронизированную версию registry template; metadata
исправлена, никакая публикация registry/PyPI не выполнялась. Native-проверки
не запускались и deselected не засчитываются. Wheel и installed metadata/stdio
теперь приняты; самостоятельная internal/public native-приёмка B1 остаётся.

Добавлены чистые определения `RectangleSketch` / `BlindRectangleExtrusion`
и внутренние native-мосты в `cad_rectangle_construction.py`. Создание эскиза
и выдавливание имеют отдельные receipts: второй шаг заимствует точный baseline
sketch, а его восстановление удаляет только созданную extrusion с flags0.
Потерянный ответ, pending close, повтор receipt, foreign/changed sketch,
неполный dependency inventory и malformed deletion ACK не разрешают
автоматическое удаление или повтор. Имена по-русски, входные длины/ссылки явные.

Связанные source pure: **117 passed, 0,66 с**, включая artificial native-stage
tests и регрессии прежнего строителя/selection scope; CAD не вызывался.
`work/pytest-rectangle-stages-4.log`. Промежуточная команда stages2 не запустила
тесты из-за неправильного имени файла; успешные stages3/4 выполнены отдельно.

Это **не завершение B1**: full supported session/target checkpoint, классификация
точного прямоугольного профиля, postconditions, домен, runtime/MCP-фасады,
самостоятельные sketch IDs и installed/native/public gates ещё требуются.
Мосты не включены в публичный каталог или native-адаптер runtime. Установленный
dev89, его package/helpers и последовательная L3-приёмка не менялись.
Исторические bundled-операции ниже не подменяют отдельную цепочку plane/sketch/extrude.

Следующий source-шаг: `rectangle_snapshot.py` / `cad_rectangle_snapshot.py`
задают полное пассивное наблюдение пустой детали, отдельного закрытого
прямоугольного эскиза и основания через прежний full body oracle. Сохраняются
properties/material/units/annotations/auxiliary/display/configuration,
equations/external/dependencies, native origin/planes, dimensions/relations
и bijective native anchors. Event/config/model/feature changes во время
getters и неполные данные отвергаются; Native watch освобождается в finally.
Отдельный sketch-builder явно перестраивает закрытый эскиз.
Related128 source pure passed/1,38 с, `work/pytest-rectangle-snapshot-2.log`;
это искусственный SDK, не installed/native. Первый прогон127/1 failed
отражал неверный ожидаемый тип отказа NaN в тесте; действующий finite-JSON
запрет сохранён. Домен/global session guard, runtime/фасады и native B1
ещё не готовы; новые snapshot/mixin не подключены к runtime-адаптеру.

Добавлена read-only подготовка в `rectangle_construction_catalog.py`: целевой
empty/sketch stage, полная поддержанная сессия и два наблюдения каждой модели,
точное разрешение ссылки через FeatureCatalog, frame/controls/name checks,
полная ревизия с параметрами и данными соседа. Whole-prepare watches охватывают
все baseline parts и освобождаются через ExitStack даже при poll failure.
Related57 source pure passed/0,50 с (`work/pytest-rectangle-preparation-2.log`):
revision меняется при изменении соседа без изменения target stamp; чужие refs,
unsupported target states и neighbor edit-and-undo отвергаются. Предыдущий
прогон53/4 failed относился к ошибкам новой тестовой обвязки параметров/props;
исправлен отдельно. Native execution_available=false: executor/checkpoint,
post-release proof/recovery, фасады и native-приёмка остаются.

В `rectangle_postconditions.py` добавлено независимое admission эскиза:
проверяется новая fully-defined геометрия реальным rectangle classifier,
точное имя/два driving размера, созданный native ID, сохранность baseline
features/anchors/origin/data, соседей/files/UI и наличие всех новых point/line/
dimension anchors. Parameter marker, объём или stamp не подменяют эту проверку.
Related75 source pure passed/0,59 с (`work/pytest-rectangle-postconditions-3.log`),
artificial SDK. Первый прогон73/1 failed относился к D1/D2 в fixture вместо
обязательных русских имён; fixture/relations исправлены, контракт сохранён.
Эта функция не разрешает native-запись: durable executor/receipt/guard release
и recovery ещё должны быть реализованы и приняты.

Добавлен независимый `verified_rectangle_extrusion` в
`rectangle_extrusion_postconditions.py`: точный переход sketch→blind base,
сохранность исходного эскиза/opaque-полей/PID, qualified dimensions,
явный ownership/dependency delta, русские имена и полный box BREP с native
blind/no-thin/no-draft controls. Related source pure: **123 passed, 1,49 с**,
`work/pytest-extrusion-proof-03.log`, искусственный CaptureAdapter и реальные
classifiers. Дополнительные native dependency links остаются неподдержанными;
последовательность parent/child и absorbed links сверена с `cad_features.py`.
Новая annotation проверяется по полной объявленной структуре и anchor,
body metadata — по имени/visible и типизированной паре material.
Executor/recovery, публичная регистрация и installed/native B1 не приняты;
установленный dev89 и завершённая L3-приёмка не изменены.

`rectangle_construction_execution.py` добавляет immutable application-wide
checkpoint, full prewrite revision, exact reference/target identity и
независимый sketch/base admission после освобождения guard. Native-мосты
записывают pending до эффекта и returned только после нормального ответа;
COM handles никогда не сериализуются. Потерянный ответ или запись журнала
блокирует inverse/retry. Восстановление допускает только полный доказанный
own effect и reacquires отдельный журналируемый guard после release; чужая
дельта или неполное восстановление сохраняет unknown/hold. Документ, сосед,
files/UI/anchors проверяются полностью, документированные target counters
не скрывают отсутствующие поля или изменённый dirty flag.

Первый связанный executor-прогон16 failed/23 passed выявил неверный путь
checkpoint-поля в artificial guard, второй подтвердил ту же ошибку; поле
исправлено по реальному JobStore, затем39 passed/1,27 с. Это не CAD-отказы.
Native-step bridge отдельно119 pure passed/1,46 с. Итог связанного B1 контура
фиксируется после последней проверки ниже; полный pure/build запускается
после законченных фасадов перед новым wheel, а не после каждой правки.

Итог связанного исходного контура: **194 pure passed, 3,01 с**, без CAD,
installed или MCP-приёмки; `work/pytest-rectangle-executor-final-2.log`.
Проверены обе стадии, реальный JobStore/MutationCoordinator, replay/conflict,
stale до записи, lost ACK, foreign delta, guard-release/storage failures,
восстановление под вторым guard и отказ неполного восстановления. Runtime
остаётся на dev89 с75/23; новых tools/list пока нет.

## Исторические принятые bundled-сценарии

Установленный dev51 принят для цепочки «новая деталь → пластина 40 × 20 × 10 мм → сквозной угловой вырез 10 × 5 мм»: **2426 pure passed, 323 CAD deselected; fresh same-wheel internal 6 native passed и public MCP stdio 7 native passed, оба accepted=true**. Каталог — **28 инструментов, 7 mutations**. Подтверждены полный L-образный BREP (12 вершин, 18 рёбер, 8 граней), независимые native объём около 7500 мм³ и площадь 2700 мм², internal stale-отказ и scoped restoration после настоящего создания выреза, публичный повтор request_id без второй операции и сохранность исходной детали/выделения/вида. Свои модели закрыты, флаг свободен, non-STL настройки сохранены. Это ограниченная приёмка указанной цепочки; исторические проверки других scope не засчитываются за новые прогоны dev51. Импорт/экспорт отложены, стадия 1 открыта. См. [PART_CUT.md](PART_CUT.md).

Историческая приёмка dev49: **2380 pure passed, 323 CAD deselected; fresh same-wheel internal 11 native passed и public MCP stdio 11 native passed, оба accepted=true**. Каталог сохраняет **26 инструментов, 6 mutations**. MCP создаёт документ и пластину 40 × 20 × 10 мм, меняет ширину на 45 мм, высоту на 25 мм и толщину на 12 мм: независимый native объём `13500.000000000004` мм³. Подтверждены stale-отказ до записи, отсутствие повторной записи request_id, сохранность исходной детали/выделения/вида и internal scoped restoration после настоящего setter/rebuild. Свои контрольные модели закрыты, флаг свободен, non-STL настройки сохранены. Импорт/экспорт отложены, стадия 1 открыта.

Историческая внутренняя приёмка создания документа:

Dev40 принят внутренней установленной native-проверкой: **2284 pure passed, 323 CAD deselected; 6 native passed, accepted=true**. Добавлено создание нового документа по существующему настроенному `.prtdot`: контроль SHA256 шаблона, явная application-ревизия, durable checkpoint, собственный `CommandInProgress`, блокировка и сохранение выделения существующих деталей. Первый scope ограничен пустой сессией или уже открытыми деталями без редактируемого эскиза, пустым шаблоном с одной конфигурацией, русским заголовком и конфигурацией. Сборки/чертежи в исходной сессии пока отвергаются. Откат закрывает без сохранения только точный новый документ, возвращённый `NewDocument`; чужие модели и неизвестные результаты не закрываются и не повторяются.

Приватный отчёт: `work/native-document-creation-dev40-1/report.json`. Wheel SHA256 `2de0302ced74cf91471b83e756bc310e6b263217c8427513a0b278f9b09c7862`, исходный commit `1528f4bdb01e778ed1613afffe8115828552cfd2`. Проверены отказ stale до записи, NewDocument из пустой сессии, искусственный известный сбой после реального создания со scoped closure/восстановлением исходной сессии, создание второй детали с сохранением первого выделения/вида, построение пластины и толщина 12 мм, 9600 мм³. Свои детали закрыты, флаг свободен. Это внутренняя приёмка, без MCP-фасада.

Установленный dev41 принят: **2290 pure passed, 323 CAD deselected**, artifact/installed metadata со всеми **23 инструментами**; fresh same-wheel internal **6 native passed** и public MCP stdio **6 native passed**, оба `accepted=true`. Публичные `document_list_templates`, `document_prepare_create_part`, `document_create_part` завершают первую цепочку: настроенный шаблон → новый документ → прямоугольное основание → толщина 12 мм, 9600 мм³. В публичном запуске оба документа создал сервер; подготовительный код не вызывал NewDocument. Повтор request_id не создал второй документ. Исходная деталь, её выделение с меткой 7, вид и геометрия сохранены, собственные модели закрыты, command flag свободен.

- Wheel `2.0.0.dev41`, исходный commit `1fc8d4b85ffc80c9d67c895013eab74808dd773a`.
- SHA256 wheel: `2484a03453b09e0904b9dbd72d90d5c577d26c4171e508001f1712bada9db10f`.
- Приватные отчёты: `work/native-document-creation-dev41-1/report.json`, `work/native-document-mcp-dev41-1/report.json`, `work/metadata-dev41-1.report.json`. Старые отчёты dev40 не заменяют fresh same-wheel приёмку.
- SHA256 верификаторов: internal `7721da28b056baaa71100fdf5579632479be6755671e41c97896b8e6cccb1d56`, public `0a76abe9ae204eb05afe0108589f2a9070f1867e8e506a8a09649ee1a590baf2`. Source digest wheel `c7f03216712678e3de9356f4afbcfda7fe3f882f8c0825e183021baa987f6fdc`.
- Операционная ревизия нового документа — `new_empty_part_document_v1`; explicit `application_id` отображается в durable `document_id` при пустой `configuration`, настоящий `doc_*` возвращается в `after.created_document_id`.
- Настроенный default-шаблон не объявляется утверждённым корпоративным шаблоном; файл шаблона не изменяется и не попадает в Git.
- Стадия 1 открыта: следующие блоки — полное поддерживаемое чтение геометрии/ограничений эскиза, безопасное изменение ширины/высоты, расширение базовых операций. Сборки/чертежи в исходной сессии, сохранение документа, произвольные шаблоны, импорт/экспорт и полный откат произвольного документа этой приёмкой не проверены.

Семантическая область ревизии — metadata открытых документов, конфигурации, stamp/save flag, активный документ, видимость и виды. Это не полная ревизия произвольных add-in данных. Документ хранится в памяти: `SetTitle2` задаёт заголовок без сохранения файла ([SOLIDWORKS API](https://help.solidworks.com/2022/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~SetTitle2.html)). Верификатор `scripts/verify_document_creation.py` проверяет реальные NewDocument/SetTitle2/переименование конфигурации, отказ stale, scoped closure, сохранность исходной детали и последующее построение/изменение пластины; его наличие не означает успешную приёмку.

В установленном dev38 принята внутренняя цепочка: scoped rollback после искусственного сбоя → пластина 40 × 20 × 10 мм, 8000 мм³ → толщина 12 мм, 9600 мм³. Три native-сценария и закрытие собственных деталей прошли; исходное выделение плоскости с меткой 7 и вторая деталь сохранены. Исполнитель использует durable checkpoint, модельный guard, временный список выделения, точные native-ссылки, русские имена, три размера и полный BREP с восемью ожидаемыми вершинами. Неизвестный native-вызов не повторяется; исходные и чужие зависимые элементы не удаляются.

Dev36 не принят: у ISketch отсутствовал ошибочно использованный GetFeature. Dev37 доказал построение и откат, но полная цепочка не принята из-за выделения после изменения размера. Dev38 разрешает элемент по канонической связи IFeature.GetSpecificFeature2 и сохраняет выделение вокруг размерного изменения/перестроения с повторным получением транзитного ISelectionMgr. Прежние отчёты и неизвестное задание dev36 сохранены; контрольные документы закрыты самостоятельно по решению пользователя.

Установленный dev39 публикует `part_prepare_base_extrusion` и `part_create_base_extrusion`; каталог — 20 инструментов. Полный локальный набор: **2265 pure passed, 323 CAD deselected**. Fresh same-wheel internal: **3 native passed**; public MCP stdio: **4 native passed**, оба отчёта `accepted=true`. Внутреннее построение/откат/редактирование дополнительно приняты на двух остальных штатных плоскостях: по 3 native-сценария. Все четыре запуска закрыли собственные модели и освободили принадлежащий проверке флаг.

Исторический dev39 MCP проверил подготовку и создание пластины, отказ устаревшей ревизии до записи, повтор request_id без второго построения, получение постоянной ссылки на толщину и её изменение до 12 мм; независимое native-чтение подтвердило 9600 мм³. Исходное выделение плоскости с меткой 7 и вторая деталь сохранены. В том scope документ создавал только setup верификатора; входом была уже открытая активная пустая деталь. Редактирование ширины/высоты эскиза и произвольные смещённые плоскости остаются расширениями. Приёмка этого scope не завершает первую стадию.

- Wheel `2.0.0.dev39`, исходный commit `89c832e48bea49642524e86890cbd73cd2ed4efa`.
- SHA256 wheel: `44dbafb8e44db49a00be4c96422eee499c422e8eacc2915c332ac4d2e366f691`.
- Приватные отчёты: `work/native-part-construction-dev39-1/report.json`, `work/native-part-mcp-dev39-1/report.json`, `work/native-part-construction-dev39-plane2-1/report.json`, `work/native-part-construction-dev39-plane3-1/report.json`.
- Принятый public verifier SHA256: `bdd7949bfcfb438eeec017d6e544bf198ba9b7fcfe192dd7600acd5104bebd6e`. Internal основной: `a8cadee812796ae9225db3e77827b801485c3484e18014550be78e9511f6bccb`; две дополнительные плоскости: `0cc83bfeb2647540e66ad6829135e4a2b224dcfb102cc49cc2cb61038b0373c7`.
- Offline artifact и installed metadata/std io приняты. STL, файловый обмен, произвольная геометрия, PDM/Simulation и полный откат документа этой приёмкой не проверены.

Цель: собственная «Контрольная пластина», параметрический прямоугольник 40 × 20 мм, выдавливание 10 мм (8000 мм³), затем изменение толщины до 12 мм по устойчивой размерной ссылке (9600 мм³). Импорт и экспорт не входят в эту цепочку.

## Реализованная подготовка — кандидат dev35

`PartCreationCatalog.prepare_base_extrusion` — внутреннее чтение, пока без регистрации MCP и без построения геометрии. Вход проверяется до CAD-вызовов: размеры в мм, конечные положительные значения не менее 0,001 мм, русские имена эскиза, операции и тела, явная непрозрачная ссылка `feat_*` на плоскость.

Первый поддерживаемый вход: активная пустая деталь с одной конфигурацией, без тел, пользовательских эскизов и размеров, без ожидающего перестроения, ошибок операций, внешних ссылок, уравнений, таблицы параметров и производных элементов. Режим редактирования эскиза и read-only отвергаются. Занятые имена не получают автоматических суффиксов.

Плоскость разрешается через постоянную ссылку в конкретном документе и конфигурации. Читается полный `IRefPlane.Transform`; первый сценарий ограничен ортонормальной плоскостью с единичным масштабом в начале координат модели. Чужая, подавленная или заменённая плоскость не подменяется первой найденной плоскостью или совпадающим именем.

Ревизия подготовки включает полную существующую область размеров, управления и поддерживаемой геометрии, параметры задания и трансформацию плоскости. Парные снимки и повторное разрешение ссылки проверяют изменения во время чтения. Результат содержит ожидаемые объём и площадь, но `native_creation_available=false`.

Документация API: [IRefPlane.Transform](https://help.solidworks.com/2022/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IRefPlane~Transform.html). Чтение трансформации не доказывает построение эскиза или выдавливания.

## Проверки и дальнейшая реализация

82 искусственных теста проверяют вход, преобразования, принадлежность ссылок, ограничения состояния, конфликты имён и конкурентные изменения. На стабильных исходниках dev35 полный набор: 2237 passed, 323 CAD deselected. Это не native-приёмка.

`scripts/verify_part_preparation.py` прошёл свежий запуск на установленном wheel без `PYTHONPATH`: **8 native passed, accepted=true**. Проверены три реальные плоскости, подготовка толщины 12 мм и отказы для чужой ссылки, неверного размера, английского имени и имени плоскости вместо постоянной ссылки. Независимо подтверждены сохранность моделей, выделения с метками, положения вида и настроек вне отложенного STL. Собственные контрольные пустые детали закрыты, флаг освобождён. Это приёмка подготовки, не построения геометрии.

- Пакет: `2.0.0.dev35`, исходный commit `9fc6cca96b7f2f0bf8e98cd350023f7598d07b15`.
- SHA256 wheel: `e5c8096f064c0784c3803282c0f317ca797a7ace35042276ac90c814d9c1ddc4`.
- SHA256 принятого верификатора: `b0fd067a72f55fea4f3b25944d04dae28a0ee67c244fb350bb0ca42ab8ad64e4`; исправление только верификатора сохранено commit `b8729f3`.
- Приватный отчёт: `work/native-part-preparation-dev35-2/report.json`; первый отчёт сохранён отдельно с `accepted=false` из-за неверных аргументов функции сравнения настроек, а не ошибки CAD-построения. Новая попытка не перезаписывает этот результат.
- Offline artifact и installed metadata/std io подтверждены; публичный каталог остаётся 18 инструментов. Импорт, экспорт, STL, создание детали и публичная операция построения этим запуском не приняты.

Следующий шаг после dev41: полное поддерживаемое чтение геометрии/ограничений эскиза и безопасное изменение ширины/высоты, затем расширение базовых операций детали. Создание нового документа через MCP уже принято. Новые возможности получают собственный явный scope, ревизию и same-wheel/MCP/native-приёмку; неизвестный исход не повторяется. Общая обязательная приёмка первой стадии остаётся открытой.
