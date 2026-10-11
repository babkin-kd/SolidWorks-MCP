# Закрытие чистых native-документов: кандидат L1

Реализованы `document_prepare_close_native` и `document_close_native`.
Статус на подготовке dev85: pure/installed/native/MCP-приёмка выполняется;
реализация сама по себе не закрывает S1-15 или стадию1.

## Контракт

Явные document_id, активная configuration, expected_revision и request_id.
Полный двухпроходный census моделей и окон, metadata/config/update stamps,
views/edit modes/visibility, native dependency paths и fingerprints,
UserControl/Visible/current directory/search folders. Список GetDocuments
сверяется с GetFirstDocument/GetNext; окна — Frame.ModelWindows/count,
IModelWindow.ModelDoc и64-bit HWndx64. Относительные/неразрешённые ссылки,
redirect/reparse ancestry, неполный census, чужие UI locks запрещены.

Dev83 native остановился на fixture setup до MCP-close: вставка компонента
пометила source part dirty. Все5 точных собственных моделей закрыты после
terminal отказа; jobs отсутствуют, baseline empty/free. Read-only probe нашёл
ещё один реальный риск: Extension.GetDependencies вернул None при одном
компоненте. Dev84 дополнительно использует count-checked живой
IModelDoc2.GetDependencies/GetNumDependencies, as-saved
ISldWorks.GetDocumentDependencies2 и live component/drawing view paths.
Search=false на всех источниках. Пустой modern getter больше не означает
отсутствие ссылок. Native исходный dev83 не принят.

Dev84:9 internal случаев прошли, затем закрытие чертежа стало unknown при
неподтверждённой активации UI-locked survivor. Terminal-аудит подтвердил
точное исчезновение чертежа, полную сохранность двух survivors/windows/files/
settings и released CIP/UI. Текущее состояние согласовано по постоянной
авторизации, свои две детали закрыты, unknown-job сохранён без retry.
Dev84 не принят, public не запускался.

Dev85: после подтверждённого retirement разрешено однократно освободить
survivor UI locks, сохраняя CIP и selection scopes. После release повторяется
полный survivor/file/window oracle; только затем выполняется explicit activation.
На выходе повторного UnLock нет. Guard evidence отдельно фиксирует attempted/
verified activation_ui_release; неподтверждённый release остаётся unknown.

`require_clean`: target и все скрытые неактивные документы, также закрываемые
CloseDoc, должны иметь needs_save=false. Весь collateral список передаётся
явно через allowed_hidden_document_ids. Incoming references survivors к
retiring paths или file identities, в том числе `..`/hardlinks, запрещены.
Для закрываемого активного target при оставшихся окнах требуется явный
видимый active_after_document_id; неактивное закрытие сохраняет исходную
активацию. Последний документ/окно при UserControl=false закрывать нельзя.

До native-вызова сохраняются durable application checkpoint и проверка
ревизии под guard. ApplicationCloseGuard удерживает только survivors;
у закрываемых handles нет getters или UI/selection restoration после CloseDoc.
Один native void CloseDoc — только acknowledgement. Успех требует точного
исчезновения model IDs/окон, сохранения всех survivors/settings/files и
проверенной активации разрешённого survivor. Проверяются и файлы уже закрытых
моделей/их dependencies. Пределы5000 моделей/окон,512 MiB/file,2 GiB файлов.

Неизменный census после normal-return без эффекта может быть known failure.
Throwing calls, утраченные acknowledgements и изменённые неподтверждённые
эффекты дают unknown/application hold; повторный close, OpenDoc/Undo rollback,
save/rewrite, изменение UserControl/Visible запрещены. Request replay возвращает
прежнее задание; timeout ограничивает ожидание, не COM.

Scope `native_document_close_clean_v1` подтверждает retirement из проверяемого
session/window census. Полный unload внутренних данных не заявляется.
First save/open, dirty-owned discard и retained-reference close — оставшиеся
обязательные lifecycle-сценарии стадии1. Это не отложенный импорт/экспорт.

## Проверка

Домен: fake-модели, оконный census, fingerprints, hidden/dirty/ref policies,
stale, alias/dependency replacement, throw/no-effect, checkpoint/replay.
Guard/bridge: уничтоженный fake-target без getters, точный survivor release,
registered types/options, полный window/model census. Такие проверки не CAD.

Standalone `scripts/verify_native_document_close.py`: установленный wheel
без PYTHONPATH, свежий private state и собственные5 моделей; планируются
internal12/public10 случаев. Сборка/public должны совпасть по Git SHA,
source digest, version, wheel SHA256 и hashes verifier/fixture/lifecycle helper.
Публичная приёмка допускается только после принятого internal того же кандидата.
На обоих прогонах проверяются retirement assembly+явный hidden collateral,
part/drawing, dirty сосед, native files, replay/stale/retired IDs, последний
clean документ user-controlled session и empty/free baseline. Internal отдельно
проверяет inactive configuration/foreign ID. Background-risk/throw/no-effect
пока искусственные сценарии; они не объявляются native-пройденными.

[CloseDoc: скрытые документы, retained data и background shutdown](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~CloseDoc.html).
[GetDependencies: transitive paths, broken references и Search flag](https://help.solidworks.com/2019/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~GetDependencies.html).
[Frame.ModelWindows](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFrame~ModelWindows.html).
[GetSearchFolders FolderType=swDocumentType(0)](https://help.solidworks.com/2023/English/api/swconst/SOLIDWORKS.Interop.swconst~SOLIDWORKS.Interop.swconst.swSearchFolderTypes_e.html).
