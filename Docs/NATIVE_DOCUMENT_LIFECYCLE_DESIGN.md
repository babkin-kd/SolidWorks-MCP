# Проект native open/close и первого сохранения

Дата исходного проекта: 11.10.2026, параллельно приёмке Save3 dev82.
Актуальное состояние: clean L1 принят dev85 по отдельному
[контракту](NATIVE_DOCUMENT_CLOSE.md)/[приёмке](NATIVE_DOCUMENT_CLOSE_ACCEPTANCE.md).
В L2 реализованы candidate domain/MCP/live-reference graph/clean rollback и
supervisor; полный source-набор5200 passed/323 CAD deselected (69,91с).
Source-каталог71/21, installed dev85 остаётся69/20. Wheel/native open ещё не
приняты. [Точный статус L2](NATIVE_DOCUMENT_OPEN.md). L3 остаётся проектом.
Ниже проект полного lifecycle; он не устанавливает исход scoped приёмок.
Основа: [PLAN](../PLAN.md),
[S1-15 и N6](STAGE_1_REQUIREMENTS_MATRIX.md),
[текущий save-контракт](NATIVE_DOCUMENT_SAVE.md),
[процесс проверки](NATIVE_TESTING.md), [пакетная отправка](GIT_WORKFLOW.md).

S1-15 остаётся открытым до публичной цепочки создания/первого сохранения,
открытия и закрытия точных native-документов с сохранностью соседней модели.
Нейтральный импорт/экспорт и STL сюда не включаются. Успех тестового
OpenDoc6/CloseDoc в верификаторе Save3 не является реализацией v2 lifecycle.

## Порядок трёх законченных блоков

| Блок | Результат | Обязательное продолжение |
| --- | --- | --- |
| L1: закрытие | Preview полного close-impact, close-aware guard, ровно одна согласованная цель, журнал/постусловия | Hidden и referenced модели, потеря последнего документа, известный отказ и unknown |
| L2: открытие | Native file reference, application revision, explicit configuration, receipt новых моделей, восстановление UI | Dependency-resolution для сборки/чертежа, уже загруженные данные, загрязнённая соседняя модель |
| L3: первое сохранение | Запись собственного нового native-файла без перезаписи существующего, независимый readback, явная привязка итоговой модели | Все заявленные типы документов, N4 restart/holds и законченная публичная N6-цепочка |

Каждый блок готовится вместе с доменом и MCP-фасадом, затем один итоговый
pure-набор, точный installed wheel, metadata и native/internal/public проверки.
Related tests выполняются после небольших правок. После 3–5 связанных блоков
либо в конце дня — одна пакетная отправка с обязательным CI. Непринятый блок
не считается законченным ради достижения числа отправок.

## Общий контракт и checkpoint

Предлагаемые имена ниже — проект; добавлять их в tools/list только после
реализации. Все mutations используют существующие JobRunner/JobStore и
MutationCoordinator, один STA и `effect_scope=application`.

- Open: `document_prepare_open_native` возвращает server-owned application_id,
  native_file_id, точные path/type/hash, configuration и revision.
  `document_open_native` принимает эти ссылки, expected_revision и request_id.
  Несуществующий document_id открываемой модели не выдумывается.
- Close: `document_prepare_close_native(document_id, configuration, policy,
  active_after_document_id)` возвращает revision и полный impact.
  `document_close_native` исполняет ровно этот impact по expected_revision и
  request_id; имя документа не является публичным идентификатором.
- First save: `document_prepare_first_save_native` связывает точный unsaved
  document_id/configuration, destination и выбранную семантику сохранения.
  Execute получает request_id/revision; допустимая смена document_id
  объявляется в prepare и в результате, а не скрывается за прежним ID.

Два полных чтения до checkpoint и проверка под guard включают canonical
IUnknown identities живых моделей, типы/path/title, configurations и active
configuration, save flags/update stamps, native edit/read-only/view-only
состояния, views/selections, активный документ, visibility приложения,
UserControl, per-document visibility, document windows и dependency membership.
Для файлов — bounded SHA256/identity/bytes/mtime/ctime и проверка ancestry на
reparse points. Для open добавляются source/dependency fingerprints;
для first save — destination parent identity и отсутствие конечного файла.

Новый census должен различать открытое окно и referenced model, данные
которой ещё загружены. Список GetDocuments сам по себе не доказывает полного
исчезновения CAD-данных. Неполный visibility/window/dependency inventory —
known rejection до записи, а не укороченный успешный checkpoint. Бюджеты
5000 моделей/512 MiB на файл/2 GiB уникальных файлов сохраняются до отдельного
обоснования изменения; превышение не разрешает partial result.

В durable before-state хранятся declared scope, native file manifest,
expected effect, ownership receipts и planned UI transitions; нельзя полагаться
только на GetUpdateStamp. Checkpoint записывается **до** Lock/CIP/settings.
Свой CommandInProgress приобретается один раз при baseline false и
освобождается с readback; чужой флаг не заимствуется. UI Lock не является
атомарной CAS против add-ins и сторонних automation-клиентов.

После каждого native шага durable evidence фиксирует его acknowledgement и
точные собственные новые/закрытые identities. Исключение из исполняющегося
COM оставляет pending call и unknown/application hold; совпадающие наблюдения
не доказывают отсутствие эффекта. Timeout означает окончание ожидания,
queued-only cancel не отменяет исполняющийся COM. Replay request_id возвращает
прежнее задание, конфликт параметров отвергается. Неизвестное задание не
переобъявляется успешным при очистке или reconciliation.

## Владение и полномочия

Receipt связывает operation_id, connection_epoch, canonical identity,
document_id, native type/path/file identity и происхождение:
`created_by_operation`, `loaded_by_operation`, `preexisting_borrowed`.
Новый путь или разность title-списков не доказывают владение. Returned raw
model удерживается на STA и регистрируется до дальнейших getter-вызовов.
Все неожиданно появившиеся документы сохраняются как свидетельства;
им нельзя автоматически присвоить cleanup ownership.

Публичный close пользовательской сохранённой модели возможен при явной
адресации и policy `require_clean`. Автоматическая тестовая очистка имеет
другой authority: только собственные контрольные документы после terminal
вызовов, проверки владения и постусловий, по постоянному решению пользователя.
Наличие серверного receipt само по себе не разрешает потерять последующие
ручные изменения. Policy `discard_owned` допустима лишь как явно запрошенный
режим для конкретного собственного документа с актуальным полным preview;
скрытые чужие документы в impact всегда блокируют этот режим.

После restart durable receipts не превращаются в действующие COM identities.
Старые IDs не переиспользуются; нужны отдельная сверка и reconciliation,
причём прежний unknown остаётся unknown. Простое совпадение имени/path не
возобновляет право автоматической очистки.

## L1: точное закрытие

`ISldWorks.CloseDoc(Name)` — void; результат устанавливается census и
состоянием окон, а не отсутствием исключения. По документации вызов способен
закрыть дополнительные неактивные hidden документы; referenced данные могут
остаться в памяти. Dirty-документ закрывается без сохранения. В background
сессии UserControl=false закрытие последнего документа может завершить
SolidWorks. Это свойства API, которые входят в preview, не исключения из
правила безопасности. [Официальный CloseDoc](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~CloseDoc.html).

Первый scope требует полного census и rejects:

- dirty target при require_clean, чужой/dirty hidden collateral, незавершённый
  edit mode, неоднозначный native name, changed config/revision;
- любые hidden collateral вне разрешённого списка и несогласованные входящие
  зависимости, неполное различение окон и referenced данных;
- close-impact, оставляющий ноль документов при UserControl=false. Не менять
  UserControl/Visible ради обхода отказа и не создавать скрытую dummy модель.

Поддерживаемый первоначальный impact — одна clean модель без скрытых
collateral. Для own cleanup расширение до точного согласованного множества
hidden моделей принимается отдельно. Если цель активна и остаются другие
окна, prepare требует явный active_after_document_id; исчезнувшая active
цель не может «восстановиться» после close. Для последнего документа в
UserControl=true результат active_document_id=null проверяется явно.

Нужен **отдельный close-aware execution guard**. Текущий
ApplicationModelMutationGuard держит ModelUiGuard и selection restoration
на всех исходных model handles; выход из контекста после close стал бы
обращаться к уничтоженной модели. Новый guard хранит target effects как
retirement evidence, заранее завершает собственные UI/selection scopes для
закрываемых моделей с readback и повторно проверяет impact непосредственно
перед CloseDoc. Долгоживущие guards остаются только у гарантированных survivors;
post-census подтверждает retirement без вызова методов на retired handles.
Lock на цели не обещается удержанным во время её уничтожения. Не принимать
release на уже отсутствующей модели за verified UnLock.

Native name для CloseDoc получен из заново сверенного точного handle,
не пустая строка и не stem без типа. Проверяется однозначность по полному
roster; совпадающие native names из разных каталогов блокируют запись.
Вызов ровно один. После него свежие окна/roster/входящие зависимости должны
совпасть с expected effect, дисковые файлы — с baseline, survivors — по
полному declared snapshot. Для referenced target возвращать
`ui_closed=true, data_retained=true`, когда это действительно установлено;
не обещать unload. До отдельной приёмки такой случай отвергается.

Успешный close необратим относительно unsaved RAM state. Не открывать
файл как «rollback» потери пользовательских изменений и не делать generic
Undo. Известный отказ разрешён только при доказанном unchanged baseline;
иная потеря моделей/окон/изменение survivors — unknown/application hold.

## L2: точное открытие

Кандидат bridge: `ISldWorks.OpenDoc6(FileName, Type, Options, Configuration,
Errors, Warnings)`, Options только native Silent и явно выбранный ReadOnly;
без Large Design Review, detached conversion и implicit lightweight scope.
Typed signature и константы необходимо сверить с установленной typelib31
до первой записи. Configuration для part/assembly обязательно непустая;
после вызова требуется exact readback, поскольку API при отсутствии указанной
конфигурации может использовать последнюю сохранённую. Drawing имеет явно
документированный configuration="". Путь абсолютный и тип соответствует
native extension. [Официальный OpenDoc6](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~OpenDoc6.html).

Первый положительный scope: самостоятельная native part без внешних refs.
Уже загруженный файл отвергается до COM как `native_document_already_loaded`;
дальнейшее явно согласованное reuse — отдельный контракт. OpenDoc6 может
вернуть существующие данные referenced модели без отображения нового окна;
это не owned-new модель. Fingerprint файла до/после и canonical identity
результата обязательны; errors/warnings должны соответствовать принятому
allowlist, первоначально только нули. Важно проверять оба outputs:
ненулевой model при missing referenced file не означает success.

Для сборки/чертежа prepare должен содержать точный closure manifest:
предсуществующие borrowed модели, ожидаемые новые зависимости,
referenced configurations, resolved absolute paths и hashes. Native
dependency API `GetDocumentDependencies2(Document, True, False, False)`
служит исходным inventory, не доказательством полной resolution. Searchflag=True
сам меняет current directory, поэтому запрещён в passive prepare. CWD/search
folders фиксируются; их изменение при необходимости допустимо только внутри
durable application mutation с verified restoration. Suppressed dependency
в returned list не означает реально загруженную модель.
[Официальный dependency API](https://help.solidworks.com/2023/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ISldWorks~GetDocumentDependencies2.html).

Открытие может изменить active document и вызвать notifications/add-ins.
Prepare объявляет UI policy `preserve_existing_active`; native промежуточная
активация допускается только как описанный шаг. Если исходная активная
модель существовала, восстановить ровно её через ActivateDoc3 с
UseUserPreferences=false и swDontRebuildActiveDoc, затем проверить canonical
identity/type/config/view/selection и отсутствие rebuild-изменений. Warning
needs-rebuild не следует скрывать; baseline warning принимается только по
явному whitelist с сохранностью модели. При пустом baseline результатом
может быть новая активная цель, объявленная в prepare. Скрытое глобальное
DocumentVisible-переключение первоначальному scope не требуется.
[Официальный ActivateDoc3](https://help.solidworks.com/2018/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.isldworks~activatedoc3.html).

Rollback известного неуспешного open допустим только после нормально
завершившегося native вызова: полный список owned-new, все они clean,
close-impact не затрагивает borrowed/hidden чужие модели, нет фонового quit,
survivors и UI точно восстановлены. Throwing OpenDoc6, неожиданная зависимость,
add-in правка соседней модели или недоказанный cleanup — unknown. Повторять
OpenDoc6 под новым request_id как «проверку» такого результата запрещено.

## L3: первое сохранение и отсутствие overwrite

Кандидат bridge — **IModelDocExtension.SaveAs3**, а не устаревший
IModelDoc2.SaveAs3. Предполагаемый вызов:
`SaveAs3(Name, swSaveAsCurrentVersion, Options, ExportData,
AdvancedSaveAsOptions, Errors, Warnings)`. Доступность modern метода есть
в официальном inventory; точную сигнатуру/опции требуется подтвердить в
зарегистрированной typelib и небольшом собственном native probe.
[Официальный interface inventory](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension_members.html).

SaveAs-семейство документировано как перезаписывающее writable файл.
`exists(destination)==false` перед вызовом, placeholder и внутренняя Python
блокировка не дают CREATE_NEW против внешнего процесса. Поэтому прямой
SaveAs в произвольный пользовательский destination нельзя выпускать с
обещанием атомарного no-overwrite. SaveAs Copy также не назначает итоговый
путь исходной модели. Rename staging файла на диске не меняет native path
загруженной модели. [Официальный SaveAs2 с этими ограничениями](https://help.solidworks.com/2025/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldocextension~saveas2.html?format=P&value=),
[native Copy/Silent flags](https://help.solidworks.com/2025/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swSaveAsOptions_e.html?id=2.10.1.702).

Предпочтительный исследуемый протокол no-overwrite:

1. Exact unsaved собственная part без incoming/outgoing references. Prepare
   объявляет `replacement_identity`, source document_id и final path;
   русское имя конечного файла без изменения имён библиотечных изделий.
2. Под application checkpoint создать собственный staging в том же томе и
   проверенном parent без reparse points. Native SaveAs3 Silent|Copy,
   без SaveReferenced/CopyAndOpen; clear selection только внутри verified
   preserved_selection. У исходной модели должны сохраниться geometry,
   конфигурации, path="", dirty state и UI.
3. Проверить acknowledgement/errors/warnings и staging hash. Независимый
   native readback собственного staging подтверждает полный поддержанный
   shape/features/dimensions/configuration/property scope. Без этого SHA
   не доказывает CAD-сохранение. Закрыть reader по принятому L1, source жив.
4. Публиковать staging посредством **OS atomic move с no-replace**, а не
   os.replace/copy-overwrite. Оба пути одного тома; изначально предлагаем
   только локальную файловую систему с проверенной семантикой. Destination,
   появившийся до публикации, сохраняется неизменным. Identity/hash результата
   связываются с staging receipt. Реализацию OS primitive отдельно проверить
   raced-destination тестом и native цепочкой; generic Path.rename для всех
   платформ такой гарантией не объявлять.
5. Open final через принятый L2, сравнить независимый CAD oracle, вернуть
   новый document_id и retire mapping всех source object IDs. Только после
   этого явно подготовленный close/discard exact source допустим; до него
   source unsaved не уничтожается. Результат публикует old/new IDs и final
   path, а потребитель заново адресует объекты. Native selection/view
   восстановление на заменённой модели требует проверенного mapping;
   первоначально принимать source с пустым selection и проверяемым view.

Этот вариант — составная операция с явной сменой identity, **не готовая
реализация обычного SaveAs**. До её доказательства отдельный copy/publish
результат обязан называться `copy_created`, оставлять source открытым и
не закрывать требование первого сохранения привязанного документа.

Сборки с in-context/virtual/несохранёнными refs и чертежи с refs нельзя
механически перенести на part-протокол. Нужны native reference census,
доказательство unchanged referents и корректной resolution после staging;
SaveReferenced и переименование библиотечных файлов запрещены. До их
отдельного решения scope part не закрывает всё S1-15.

После публикации неизменный final файл нельзя удалять в generic rollback,
тем более при конкурирующей замене. Filesystem side effects и partial stages
остаются в durable evidence; если source/path/итоговый open не подтверждены,
unknown/application hold с сохранённым source и опубликованным artefact.
Не повторять SaveAs, не переписывать disk baseline и не сбрасывать dirty flag.

## Минимальная приёмочная матрица

Все native модели — собственные русскоязычные временные файлы в ignored
work/. User-like соседняя dirty модель также создаётся стендом; реальные
документы пользователя в negative-тестах не закрываются. Подробные negative
кейсы выполняются internal; публичный MCP проверяет пользовательскую цепочку,
схему, journal/replay/timeout, не дублирует всю физическую матрицу.

| ID | Native проверка | Ожидаемое доказательство |
| --- | --- | --- |
| C1 | Закрытие inactive clean part рядом с dirty собственным соседом | Исчезло ровно одно окно/model; соседний RAM/disk/UI baseline совпадает |
| C2 | Закрытие active clean target с explicit survivor; последний документ UserControl=true | Exact active_after или null, приложение живо, guard release verified |
| C3 | Dirty require_clean; foreign hidden collateral; неоднозначное имя; stale/manual edit | Known pre-write failure, native CloseDoc count=0, пользовательские изменения сохранены |
| C4 | Own hidden collateral и referenced target | Точный impact и UI/data-retained distinction; до реализации — явный reject, не skipped-pass |
| C5 | Последний документ UserControl=false | Pre-write reject count=0, исходные UserControl/Visible/CIP сохранены |
| C6 | Нормальный no-op CloseDoc и throwing CloseDoc из собственного fault bridge | Unchanged known failure отдельно от pending-call unknown; нет auto reopen/retry |
| O1 | Part/config2 открывается рядом с dirty model/config1 | Новый точный ID, configuration2 и geometry readback, исходная active/UI восстановлена, файлы неизменны |
| O2 | Собственные assembly/drawing с повторными instance/config и абсолютными deps | Полный borrowed/new closure и native resolved references, no missing/foreign replacement |
| O3 | Already loaded; absent configuration; wrong type; changed source/dependency; reparse | Already loaded отвергнут до COM; API fallback конфигурации никогда не success; остальные explicit negative результаты |
| O4 | Одинаковые имена dependency в CWD и search folder | Принят только prepared exact resolution; отсутствие подтверждения блокирует scope, settings restored |
| O5 | Warning/null/partial load, add-in соседний эффект, throwing native | Known restoration только при полном baseline; иначе persistent application hold |
| F1 | Новая own part с двумя конфигурациями/двумя телами и размером | Native readback полного declared scope, final file/path, old/new ID mapping, нет silent data loss |
| F2 | Existing destination и external creation непосредственно перед publish | Оригинальный чужой fingerprint неизменен, публикация no-replace отклонена, source жив |
| F3 | Stage save предупреждение/throw, readonly parent, changed/reparse parent | Нет overwrite; explicit known/unknown по фактическому эффекту; собственные receipts сохранены |
| F4 | Incoming/in-context/virtual refs и referenced drawing | Без принятого специального протокола count=0 reject; после реализации полный reference oracle |
| J1 | MCP timeout0 → job_get → replay; conflict; restart unresolved | Native effect ровно один, request_id стабильный, unknown hold не обходится новой эпохой |
| N6 | Public create → first save → save modification → close → open/config → readback → close | Exact installed wheel, dirty сосед не меняется, terminal jobs, свой cleanup и baseline доказаны |

Нормально вернувшийся no-op и throwing COM различаются даже при одинаковом
конечном состоянии. Injected Python faults подтверждают failure protocol,
а не реальную CAD ошибку открытия/записи: native errors проверяются отдельно
на отсутствующем reference, недоступном destination и иных воспроизводимых
собственных fixtures. Пропуски идут в skipped/not_run; generic success не
публикуется из-за отсутствия сборки/чертежа/hidden кейса.

## Блокеры перед расширением scope

1. Close-aware guard и полный window/hidden/reference census пока отсутствуют.
   IModelDoc2.Visible документирован как visibility active document; нельзя
   без probe считать его достаточным getter для каждого inactive handle.
   [Официальное Visible](https://help.solidworks.com/2022/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldoc2~visible.html).
2. Native CloseDoc name disambiguation и retained-model semantics нужно
   подтвердить на установленном SW2023; документированное свойство не
   является принятием конкретного adapter inventory.
3. Современная SaveAs3 signature и Copy поведения для unsaved source должны
   быть сверены в typelib31 и own native probe. Нет подтверждённого прямого
   native CREATE_NEW/атомарного SaveAs в произвольный destination.
4. Atomic no-replace publish с identity replacement требует отдельной
   реализации/приёмки; неизвестное parent-redirection/external-write поведение
   не скрывать под проверкой `exists`.
5. Полный dependency resolution/borrowed ownership для assembly/drawing,
   inactive visibility и UI restoration после native notifications открыты.
6. Durable ownership/reconciliation после restart и итоговые N0–N6 остаются
   обязательными. Принятая историческая legacy-очистка и Save3 не заменяют
   перечисленные v2 проверки; стадия1 этим проектом не закрывается.
