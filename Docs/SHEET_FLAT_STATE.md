# Native-развёртка и обратный сгиб — принятый ограниченный сценарий

Инструменты `sheet_prepare_flat_state` / `sheet_set_flat_state`, scope
`single_l_sheet_flat_state_v1`. Проверены полный flat/fold BREP, native fixed-face,
исходная сеть размеров/K, текущий body/bundle и сохранение русских имён тела
«Тело листового уголка» и списка «Список вырезов».

**dev62 принят** на одном точном установленном wheel: **3435 pure passed /323 CAD
deselected (39,86с)**, metadata42 инструментов /14 мутаций, **internal native7 /
public MCP8 passed, оба accepted=true**. Свои документы закрыты, baseline пуст/free,
guard released; все задания terminal, новых unknown нет. Рабочая v1 сохранена.
Приёмка ограничена одним самостоятельным L-профилем/телом/конфигурацией с одним
сгибом90°. Импорт/экспорт отложены; все стадии плана остаются открытыми.

Source freeze `03ab76563b90643e3dc568f6301b30d2290a30d5`; source digest
`9190ea543d13b8b9b2681c628dad1eab62856862686b1eeb77c67a4c2cf716d4`; wheel SHA-256
`add1bfbec73dfbada9bc30aa362e77f3bdb8f5f9f363d0a5743337c2900abe39`. Installed wheel без source PYTHONPATH.
Private evidence: `work/metadata-dev62-1-report.json`,
`work/native-sheet-state-dev62-1/report.json`,
`work/native-sheet-state-mcp-dev62-2/report.json`.

Internal покрывает stale до записи, известный сбой после настоящего flat setter
и scoped restoration. Public SDK/stdio покрывает создание профиля, flat/fold,
повтор request_id без второй CAD-операции, журнал и сохранение исходной модели.
Public-прогон1 выполнил все8 CAD-кейсов, но остался accepted=false из-за ошибки
аргументов завершающего cleanup-вызова. Собственные документы были закрыты finally.
Исправлен только harness; его84 связанных теста passed. Свежий прогон2 принят
на том же wheel. Первый отчёт сохранён без переобъявления успехом.

Исторические source-пробы ниже объясняют найденные ограничения. Доменная probe2
подтвердила полное восстановление имён и формы; её private evidence:
`work/native-flat-domain-development-probe-2/report.json`.

## Инженерный сценарий и адресация

Переключить существующий собственный L-профиль между folded и flat состояниями
в одной явной активной конфигурации, сохранив параметры, размеры и русские имена.
Клиентский target — strong object_id листового основания; единственный
FlatPattern выводится через точное body membership и документированные singleton
папки. Обычный feature-resolver не позволяет редактировать подавленный элемент,
поэтому его правила не расширяются глобально ради развёртки. Имена/номера дерева
не являются способом разрешения цели. Несколько конфигураций — отдельный пункт.

K берётся из независимой native definition существующего листового металла,
включается в ревизию и сохраняется; скрытого K=.5 нет. Новая операция не меняет материал, таблицы, толщину, радиус, K, параметры исходного эскиза или
сохранять файл. Импорт/экспорт и DXF в этот блок не включены.

## Подтверждённая source-проба на SOLIDWORKS2023

Собственная несохранённая контрольная деталь W40/H20/L30/t2/r2 мм, K=.42 создана
через принятый folded-домен. До изменения состояния записан durable checkpoint,
затем получен application/model guard. SetSuppression2 использован для точного
FlatPattern: action1/0, this-configuration1, без unsuppress-dependent действия.
Приёмка нового инструмента из этой исследовательской операции не следует.

Неподвижная грань native FixedFace2 подтверждена в текущем теле: четыре угла
x4…40 мм, y2 мм, z0…30 мм и нормаль+Y. Отсюда независимо выбран fixed-leg X.
MergeFace/SimplifyBends/ShowSlitInCornerRelief=true. Getter использован без
AccessSelections, UI/rollback setters не вызывались.

Развёртка совпала с целевой формой по всем восьми вершинам, двенадцати рёбрам
и шести ориентированным planar-граням. Общий reader отдельно проверяет finite
trims, coedges/partners, связность/manifold и закрывающие native stamps.
Длина D=52+π/2*(2+.42*2)≈56,4610615681 мм, x=40−D…40 мм, y0…2 мм, z0…30 мм.
Native V≈3387,66369408585 мм³, A≈3733,50794035824 мм². Это фактическая native
развёртка, не только прогноз нейтральной длины и не bbox/census/mass shortcut.

При обратном сворачивании восстановлены **точные исходные BREP16/28/14 и три
размера**, native-параметры/K, эскиз и suppression состояния. Folded
V≈3402,74333882308 мм³/A≈3749,59289474462 мм². Для произвольного K объём folded
и flat не обязан совпадать: проверяется отдельная ожидаемая форма и её масса.

**В исторической примитивной source-пробе3 полное состояние не восстановлено:** SolidWorks автоматически
переименовал тот же CutListFolder из «Список вырезов» в `Sheet<2>`. В source-пробе
full_folded_state_restored=false; это не успешная итоговая приёмка. Имя тела
этот пробник отдельно не снимал. Позднейшая доменная проба и установленная
приёмка dev62 подтвердили сохранение обоих имён.

Получены существенные ограничения native-ссылок:

- Native CAN тела меняется при разворачивании и сворачивании. Старый IBody2
  нельзя считать текущим после rebuild; нужен новый current-body proof.
- Bytes body PID в этой пробе сохранились; production сравнение должно использовать
  IsSamePersistentID, exact текущий body membership и canonical round trip.
- PID/геометрия FixedFace меняются при объединении плоских граней. Неподвижная
  плоскость/свободный конец и полный целевой footprint доказываются для каждого
  состояния отдельно; одинаковый старый face handle не требуется через rebuild.
- Native body.GetFeatures имеет3 члена в folded и4 в flat: добавляется точный
  TemplateFlatPattern. Его необходимо связать с documented folder getter;
  нельзя просто снять ограничение на чужие body members.
- Новых/удалённых узлов дерева не появилось:33 до/после. Меняются три ожидаемых
  suppression-флага и имя того же CutListFolder; это ограниченная область эффекта.

Все четыре source-задания terminal/committed, новых unknown нет. Оба state
observation guards released, selection preserved. Свой документ закрыт без
сохранения после терминальных вызовов, non-STL preferences и пустой/free baseline
подтверждены. Общий итог source-пробы всё равно не принят из-за имени списка.

## Проверяющие примитивы и тесты

`sheet_flat_geometry.py` требует целиком подтверждённую неподвижную native грань,
а затем сопоставляет все vertices/edges/oriented face cycles с целевым flat box.
Оба fixed-leg X/Y, стороны и rigid native frame покрыты искусственными тестами;
фактическая CAD-проба выше пока проверила только X. Нельзя выбрать подходящий
box после записи, перебрав X/Y, вместо независимого fixed-face proof.

`cad_sheet_flat.py` усиливает read-only native proof: exact body/feature
membership, face PID/CAN round trip, current topology, четыре distinct native
corner/edge handles, конечные координаты/плоскость и strict options. Он не вызывает
AccessSelections, suppression, rebuild или UI setter. Этот reader испытан пока
на искусственном доменном сценарии, не через установленный новый wheel.

`sheet_flat_state.py` исключает из точного хеша только независимые mass/area
readbacks. Все исходные BREP, tree/drivers, параметры, fixed-face refs, controls
и dimension revision остаются в ревизии. Численные mass/area проверки с допуском
обязательны при закрытии capture и постусловиях.

Получены87 новых pure-тестов; весь связанный sheet-поднабор: **260 passed/1,84с**.
Это не новый полный pure-набор пакета, wheel metadata или native/MCP приёмка.
Source-probe1 остановился до FlatPattern write из-за exact mass comparison;
probe2 — до native execution, stale/not_started из-за mass round-off в revision
(около4e−13 мм³). Оба контрольных документа закрыты; ошибки не засчитаны успехом.
Probe3 использовал исправленную ревизию и полный целевой flat BREP.

Native-probe3 source digest при запуске:
`e70d092419afdb1c9c81f960797dae292a59c89fe995e666680a7cdfb6470ad2`.
Добавленный позднее усиленный native-reader не входит в эту source-пробу.
Приватные evidence вне Git: `work/native-flat-development-probe-{1,2,3}/`,
`work/sheet-flat-related-tests-2.log`; CAD-файлы/журналы публично не сохраняются.

## Реализованный контракт и итоговая приёмка

Инструменты требуют явные document_id/configuration/base_object_id/flattened;
setter также expected_revision/request_id. Подготовка читает два закрывающих
полных снимка. Durable checkpoint предшествует guard; внутри guard повторяется
полная подготовка. Ревизия включает полную геометрию/сеть размеров/параметры K,
неподвижную полку, настройки и сильные ссылки. Только redundant mass/area не
хешируются; они отдельно сверяются с ожидаемой геометрией.

Текущий body подтверждается заново после rebuild; базовый/листовой/flat/cut-list
bundle связывается через native PID/CAN/membership и singleton folder getters.
Исходные имена тела/списка сохраняются только после полного доказательства
ожидаемого изменения формы. Другие узлы и параметры не разрешены к записи.
Известный сбой восстанавливает только исходное flat/fold состояние и имена;
полный baseline проверяется. Чужое изменение или неполный native результат
оставляет unknown без автоматического повторения/Undo/удаления исходного профиля.

Граница: один самостоятельный точный L-профиль, одна активная конфигурация,
один native-сгиб90°, поддержанный фиксированный конец. Несколько тел/сгибов,
произвольные профили, материалы и сохранение/экспорт требуют отдельного блока.

Итоговая установленная приёмка выполнена; точные evidence и её границы приведены
выше. Исторические source87/260 и последние180 связанных pure-тестов не заменяют
итоговый полный набор3435 или native/MCP. Дальнейшие формы и инженерные операции
нуждаются в своей проверке; приёмка всего2.2 не заявляется.

Источники native API: [IFeature.SetSuppression2](https://help.solidworks.com/2021/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeature~SetSuppression2.html),
[IFlatPatternFeatureData.FixedFace2](https://help.solidworks.com/2016/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFlatPatternFeatureData~FixedFace2.html).
AccessSelections переводит модель в rollback и требует освобождения:
[IAccessSelections2](https://help.solidworks.com/2026/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFlatPatternFeatureData~IAccessSelections2.html).
Смысл neutral-axis allowance: [Bend Allowance and Bend Deduction](https://help.solidworks.com/2022/English/SolidWorks/sldworks/c_Bend_Allowance_and_Bend_Deduction.htm).
