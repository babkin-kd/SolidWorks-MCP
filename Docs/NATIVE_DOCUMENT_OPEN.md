# Native open: внутренняя основа L2, приёмка не завершена

Состояние 11.10.2026: подготовлены внутренний OpenDoc6 bridge, baseline guard
и пассивный файловый manifest. Public `document_prepare_open_native` и
`document_open_native` пока не зарегистрированы. Это промежуточная реализация
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

Типизированная сигнатура OpenDoc6 и passive getters сверена metadata-only
по установленной sldworks typelib31; Silent=1/ReadOnly=2 подтверждены в
swconst typelib31. CAD-документы при этой проверке не создавались и не открывались.
Справочные источники: [OpenDoc6](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~OpenDoc6.html),
[native options](https://help.solidworks.com/2023/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swOpenDocOptions_e.html?id=2.10.1.545).

## Фактические проверки

95 новых pure-cases на искусственных COM-объектах/файлах; вместе со связанными
регрессиями close/save/create/server/metadata — **263 passed,4,37с**.
Это source-проверка. Wheel для L2 ещё не собран/установлен, internal/public
native-приёмка открытия не запускалась. Dev85 остаётся точной исторической
приёмкой clean close; результаты не переносятся на изменённые исходники.

## Обязательное продолжение

1. Durable domain prepare/execute: application/native_file IDs, полная ревизия
   census+manifest, checkpoint до guard, request_id/replay/holds, revalidation
   под guard и независимые постусловия.
2. Exact returned-model receipt и подтверждение всех новых/borrowed dependencies,
   referenced configurations и actual load modes сборки/чертежа. Файлового
   списка и GetOpenDocumentByName недостаточно для принятия всей resolution.
3. Сохранность dirty соседа, файлов/views/windows/settings, явное active-after,
   no-rebuild activation, нормальный no-effect отказ и только доказуемая очистка
   owned-new. Throw/неожиданный эффект остаются unknown, без retry/adoption.
4. MCP-фасад, supervisor evidence gate и один итоговый fresh wheel с обязательной
   installed metadata, internal native и public MCP приёмкой по
   [NATIVE_TESTING](NATIVE_TESTING.md). После этого L3 first save и общий N6.

Это незавершённый L2-блок, он не увеличивает число законченных блоков для
пакетной отправки. Изменения остаются локальными; CI-fix отправится вместе
со следующим согласованным пакетом. Стадия1/20 открытых требований сохраняются.
