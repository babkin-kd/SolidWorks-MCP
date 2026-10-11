# Native open: ограниченный L2 принят dev87

L2 bounded native open принят на exact installed dev87: metadata71/21,
internal13/13 (210,07 с), public MCP11/11 (189,68 с), оба accepted=true.
Полный source pure5560 passed/323 CAD deselected (77,43 с); external cleanup
regressions — related499 passed (1,15 с). Полный baseline/CWD, dirty сосед,
resolved new/borrowed references и own cleanup подтверждены. Исторические
failed/unknown отчёты сохранены; они не переписаны и не повторены.
[Точная приёмка](NATIVE_DOCUMENT_OPEN_ACCEPTANCE.md),
[контрольная точка](CHECKPOINT_DEV87.md).

Public `document_prepare_open_native`/`document_open_native` реализованы.
Приёмка подтверждает текущий конечный manifest13 internal/11 public,
а не новые режимы загрузки или ссылок. L3/общий S1-B5 остаются открытыми;
[граница выпуска](STAGE_1_REQUIREMENTS_MATRIX.md).

## Реализовано в исходниках

- Bridge принимает абсолютный native-путь, точный тип, конфигурацию и Boolean
  read-only. Для детали/сборки конфигурация обязательна, для чертежа — пустая.
  Options только Silent либо Silent|ReadOnly; fallback, LDR и SpeedPak не выбираются.
- Receipt удерживает exact raw return до native getters и фиксирует отдельные
  attempted/pending/returned состояния. Один receipt допускает один OpenDoc6.
  Исключение остаётся pending, повтор запрещён. Возврат baseline canonical
  identity считается borrowed, владение не выдаётся по разности списков.
- Registered acknowledgement проверяет отдельно model/errors/warnings.
  Null model и ненулевые коды передаются будущему доменному oracle как
  свидетельства; bridge не объявляет их успехом или безопасным отказом.
- Guard блокирует только исходные живые модели, сохраняет их selection и
  один собственный CommandInProgress. Перед отдельной активацией разрешена
  однократная проверяемая фаза UnLock с удержанием CIP/selection. Throwing
  release не повторяется и оставляет неподтверждённые свидетельства.
- Manifest дважды читает полный saved file closure с Search=False. Проверяет
  конфигурации, native extensions, SHA256/file identity/времена, reparse ancestry,
  missing references, максимум5000 файлов/512 MiB на файл/2 GiB уникальных
  файлов всей сессии. Уже загруженный source, включая hardlink alias, отвергается.
  Borrowed dependencies связываются с точными baseline IDs; resident handle
  вне полного census не усыновляется. Граф файлов не доказывает CAD resolution.
- Prepare связывает server-owned application/native_file IDs с полной ревизией
  census/manifest. Execute повторно проверяет её под baseline guard; checkpoint
  сохраняется до guard. Каждый OpenDoc6/release/activation/rollback-close шаг
  имеет durable pending/returned запись в существующем schema3 journal.
  Normal return не снимает hold: нужен независимый final oracle. Pending шаг
  запрещает финальную committed/rolled_back verification и автоматический retry.
- Baseline и новый loaded graph дважды проверяются через exact GetModelDoc2/
  ReferencedDocument handles, paths и referenced configurations. Все новые
  модели должны быть достижимы из exact returned root; все saved dependencies
  должны соответствовать live receipts. Borrowed baseline остаётся неизменным,
  включая dirty/modes/views/windows/file hashes/settings/live references.
- После normal failure допускается доказанный no-effect или require-clean
  закрытие ровно owned-new root/hidden dependencies. Close impact независимо
  проверяет dirty/incoming references/foreign hidden/background quit risk.
  Retired handles после CloseDoc не читаются. Очистка и отдельная no-rebuild
  activation сохраняют ledger и повторную проверку исходного состояния.
- Фасад строго проверяет Boolean read_only/finite bounded timeout; default
  read_only=False входит в durable arguments. Request replay не повторяет COM;
  application hold сохраняется при pending/foreign/неподтверждённых эффектах.
- Пассивный supervisor отдельно проверяет exact Open guard и native ledger:
  завершённые one-shot пары, scope/IDs/typed ACK, source binding, clean rollback
  impact и exact activation target. Raced busy проверяется отдельным prewrite
  gate. Этот gate не заменяет доменный oracle и не закрывает CAD-фикстуры сам.

Начальный scope `native_document_open_resolved_v1` консервативен: нужны saved
resolved assembly components. Lightweight/SpeedPak/virtual/suppressed reference
mode и part external-reference handles ещё не приняты. Поддержка произвольных
режимов загрузки и полного lifecycle этим кандидатом не объявляется.

Типизированная сигнатура OpenDoc6 и passive getters сверена metadata-only
по установленной sldworks typelib31; Silent=1/ReadOnly=2 подтверждены в
swconst typelib31. CAD-документы при этой проверке не создавались и не открывались.
Справочные источники: [OpenDoc6](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~OpenDoc6.html),
[native options](https://help.solidworks.com/2023/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swOpenDocOptions_e.html?id=2.10.1.545).

## Фактические проверки: история подготовки кандидатов

Основа:95 новых pure-cases; related263 passed/4,37с. Новые domain69 passed/5,32с,
facade76 cases (related86 passed/1,07с), bridge/ledger related99 passed/0,64с;
интеграция domain/facade/server/metadata/ledger188 passed/7,90с. Эти связанные
наборы перекрываются; их числа не суммируются. Все сценарии искусственные,
без CAD-вызовов. Первый wheel L2 dev86 собран/установлен из чистого c512a6e;
installed metadata71/21 принята. Internal native запускался, но не принят;
public не запускался. Dev85 остаётся точной исторической
приёмкой clean close; результаты не переносятся на изменённые исходники.

После объединения независимых участков: supervisor evidence211 pure/0,22с,
Runtime14 pure/1,25с, supervisor integration57 related pure/1,56с.
Итоговый полный source-набор — **5200 passed,323 CAD deselected,69,91с**,
ignored log `work/pytest-open-full-1.log`. Пропуски CAD не засчитываются.

Dev86: итоговый pure5427 passed/323 CAD deselected/69,60с, отдельный
preflight20 passed/0,76с. Первый native-прогон остановился в подготовке чертежа:
в русской установке native model view — `*Изометрия`, а не `*Isometric`.
Выбор точного имени из passive inventory и дополнительная запись ownership
после SetTitle2 исправлены; related257 passed/0,98с, включая preflight30.
Только собственные4 фикстуры закрыты; CAD-операции v2 ещё не вызывались.

Второй internal-прогон: prepare завершён; OpenDoc6 normal returned-new с ACK0/0,
но CWD перешёл из исходного каталога в source.parent. Полный baseline исходной
dirty детали остался неизменным. Итог unknown/unresolved/0 accepted cases;
это не успех открытия и не разрешение повторять request. После terminal native
и независимого census закрыты только2 exact-owned private fixtures, исходный
CWD восстановлен; historical unknown/hold в журнале сохранены. Public gate
не запускался. Приватные CAD/journals/полные пути остаются в ignored work/.

В исходном dev87 реализован explicit one-shot `restore_directory_native` с pending/returned
ledger и окончательной строгой проверкой полного baseline. Только промежуточный
CWD от normally-returned OpenDoc6 к bound source.parent может быть восстановлен;
foreign CWD/settings/model/file changes, pending/throw/journal failures запрещают
setter/автоматическую cleanup. Родной setter=False/nonbool ACK, пропавший
baseline directory и сбой receipt factory также удерживают unknown без close.
Связанные domain123/11,33с, bridge101/0,48с, passive gate238/0,24с,
supervisor integration13/1,56с; наборы перекрываются и не суммируются.
Итоговый полный pure — **5560 passed,323 CAD deselected,77,43с**,
ignored log `work/pytest-open-dev87-full-1.log`. На этом историческом checkpoint
fresh dev87 wheel/internal/public ещё впереди; итоговая приёмка записана ниже.
Source/pure сами по себе не заменяют native-приёмку.

## Завершение текущего блока и следующий остаток

Exact installed dev87 принят internal13/public11 с одинаковыми final helper
hashes. Сначала исправлены два external verifier дефекта: неверный read-only
getter и смена active при own drawing cleanup. Пакет после wheel не изменён;
whole failed отчёты сохранены. Связанные499 pure прошли; подробные hashes,
время и native/fault-probe границы — в [приёмке](NATIVE_DOCUMENT_OPEN_ACCEPTANCE.md).

Следующий блок — L3 first save только own unsaved part1cfg/1solid/no refs,
затем остатки B1–B4 и same-wheel B5. Unsupported load/reference/dirty-owned/
retained-reference области видны как D2-LOADREF/D2-CLOSE/D2-DOCUMENTS;
в завершённый L2 новые случаи не добавляются. Гарантии сохраняются.

Это второй законченный lifecycle-блок после пакетной отправки dev82:
clean close dev85 и bounded open dev87. Изменения/CI-fix остаются локальными
до 3–5 законченных блоков либо конца рабочего дня. Стадия1 открыта.
