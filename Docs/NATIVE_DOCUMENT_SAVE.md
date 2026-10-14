# Сохранение текущего native-файла

Принят dev82: `document_prepare_save_native` /
`document_save_native`, scope `native_document_current_file_save_v1`.
Каталог67 tools/19 guarded operations; internal10/public5 accepted=true на
одном wheel. [Точная приёмка](NATIVE_DOCUMENT_SAVE_ACCEPTANCE.md). Общий N6 открыт.

Точные document_id, активная configuration, prepared revision и request_id.
Деталь, сборка или чертёж должны уже иметь существующий native-путь.
Один штатный IModelDoc2.Save3 с Silent=1; SaveReferenced не устанавливается.
Нет implicit activation, SaveAs/rename/copy, изменения библиотечного имени,
сброса read-only или PDM check-out. Первое сохранение, open/close — отдельные
обязательные остатки S1-15, этот блок не сокращает их область.

Перед записью два полных census связывают canonical document identities,
metadata/update stamps/configurations/save flags, read-only/edit/view-only
состояния, views, активный документ и visible. Все открытые native-файлы
fingerprinted по path/identity/bytes/SHA256/mtime/ctime. Unsaved соседняя модель
остаётся в application checkpoint, но не получает выдуманный file fingerprint.
Symlink/junction в файле или ancestry отвергается. Ограничения5000 моделей,
512 MiB/file и2 GiB уникальных путей; partial checkpoint не публикуется.

В обычной сборке root edit target не является in-place редактированием.
В чертеже штатный активный sketch листа определяется по canonical identity
GetFirstView().GetSketch(); template/другой sketch блокируется. Полный список
листов и current sheet входят в revision/postconditions. Save3 может обновить
заголовок окна после прежнего переименования листа: допускается только точный
заголовок из неизменных native path/current sheet, другие title-изменения запрещены.

После durable application checkpoint и verified command/UI/selection guard
повторно сверяются revision и файл. Native True, errors=warnings=0,
needs_save=false, сохранность path/config/view/activation обязательны.
Post-state содержит новый file fingerprint; все остальные открытые модели
и их файлы должны совпасть с исходными. Save-related update stamps и
observation tokens целевой модели могут измениться. UI/selection guard release
также входит в durable committed evidence.

Revision является **наблюдением lifecycle/file state**, не полной BREP или
произвольного add-in состояния. Guard не обеспечивает атомарную filesystem CAS
для сторонних процессов. File SHA и native acknowledgement не заменяют общий
geometry roundtrip gate. Общие ревизии/конкурентность/1000+ performance остаются
в матрице и не объявляются закрытыми.

Бросивший исключение Save3 сохраняет pending native call и unknown/application
hold даже при одинаковых последующих наблюдениях. При нормально возвращённом
отказе возможен known failed только если полный declared baseline не изменился.
Если файл/модель уже изменились, нет automatic disk rewrite/delete/Save3 retry
или reset save flag. Повтор request_id получает исходное задание; тайм-аут
ограничивает ожидание, не отменяет COM. Новый write блокируется до согласования.

Подготовлен standalone installed-wheel стенд `verify_native_document_save.py`:
internal10/public5, реальная размерная правка детали, свойство сборки и имя
листа чертежа. Internal читает обратно отдельные собственные копии файлов;
это независимый native oracle сохранения, а не приёмка ещё отсутствующих
v2 open/close. Весь CAD/журнал/отчёты остаются в ignored work/.

Сигнатуры дополнительно сверены с зарегистрированными type libraries31.2.1.
Основные ссылки: [Save3](https://help.solidworks.com/2022/English/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldoc2~save3.html),
[IsOpenedReadOnly](https://help.solidworks.com/2024/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDoc2~IsOpenedReadOnly.html).
[CloseDoc](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~CloseDoc.html)
также может закрывать неактивные hidden документы и сохранять referenced data
в памяти; эти последствия требуется учесть в следующем блоке close.
