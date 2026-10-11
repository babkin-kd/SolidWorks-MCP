# Native open: кандидат L2, приёмка не завершена

Состояние 11.10.2026: к bridge/guard/manifest добавлены durable domain,
exact live-reference graph, require-clean rollback и MCP-фасад с lazy Runtime.
Public `document_prepare_open_native` и `document_open_native` зарегистрированы
в исходном кандидате (каталог71 tools/21 mutations), установленный dev85
сохраняет исторический каталог69/20. Это промежуточная реализация
[L2](NATIVE_DOCUMENT_LIFECYCLE_DESIGN.md), а не завершение S1-15/N6.

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

## Фактические проверки

Основа:95 новых pure-cases; related263 passed/4,37с. Новые domain69 passed/5,32с,
facade76 cases (related86 passed/1,07с), bridge/ledger related99 passed/0,64с;
интеграция domain/facade/server/metadata/ledger188 passed/7,90с. Эти связанные
наборы перекрываются; их числа не суммируются. Все сценарии искусственные,
без CAD-вызовов. Wheel для L2 ещё не собран/установлен, internal/public
native-приёмка открытия не запускалась. Dev85 остаётся точной исторической
приёмкой clean close; результаты не переносятся на изменённые исходники.

После объединения независимых участков: supervisor evidence211 pure/0,22с,
Runtime14 pure/1,25с, supervisor integration57 related pure/1,56с.
Итоговый полный source-набор — **5200 passed,323 CAD deselected,69,91с**,
ignored log `work/pytest-open-full-1.log`. Пропуски CAD не засчитываются.

## Обязательное продолжение

1. Подготовить exact-owned native fixtures/verifier: деталь/сборка/чертёж,
   new/borrowed dependencies/configurations/load modes, dirty baseline,
   active-after, replay/stale, известные отказы и безопасная очистка.
2. Один итоговый fresh wheel с обязательной installed metadata, internal native
   и public MCP приёмкой по
   [NATIVE_TESTING](NATIVE_TESTING.md). После этого L3 first save и общий N6.
3. Отдельно закрыть неподдержанные load/reference/dirty-owned/retained-reference
   области по конечной матрице; scoped L2 не закрывает всё S1-15.

Это незавершённый L2-блок, он не увеличивает число законченных блоков для
пакетной отправки. Изменения остаются локальными; CI-fix отправится вместе
со следующим согласованным пакетом. Стадия1/20 открытых требований сохраняются.
