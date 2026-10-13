# Конечная приёмка B2 на dev96

B2 остаётся открытым. Привязка кандидата, full pure8427/323 и installed83/27 —
[контрольная точка](CHECKPOINT_DEV96.md). Результат positive suppression/return
dev95 сохранён отдельно; он не принимается за результат dev96.

| Условие B2 | Пользовательский результат | Требуемое доказательство на dev96 | Текущий статус |
| --- | --- | --- | --- |
| N1 | Driving depth10→12 мм, объём8000→9600 мм³ | Публичный dimension ID/revision/request; actual scalar readback, rebuild и полный независимый BASE, включая соседнюю модель | Ещё не принято на dev96 |
| N2 | Русское имя элемента; прежняя адресная ссылка действует | Public rename/readback, прежний object ID и PID/canonical membership; полные данные отличаются только разрешённым именем | Ещё не принято на dev96 |
| N3 | Подавить и вернуть собственное основание | Public suppression/return с original ownership, full bodyless/BASE snapshots, исходный sketch/DIMs/PID и имя тела; checkpoint/guards/replay | Dev95 positive принят; dev96 ещё не принят |
| N4 | Preview точного own leaf, затем удалить только основание | Read-only prepare, full BASE→SKETCH, exact deleted ID, preserved sketch, actual raw old PID1/4+null, удалённый ID отвергается при чтении; SQL/replay | Native delete committed/replay подтверждены; independent neighbor read failed. Отдельная own cleanup/baseline принята; positive gate остаётся failed |
| N5 | Безопасный отказ для stale/foreign/dependent/linked/неполного scope | No-write/known-no-effect evidence реальных refused jobs; полный снимок, отсутствие native dispatch/checkpoint где применимо; unsupported CAD cases видимы отдельно | Pure отказы есть; конечная installed/native приёмка не завершена |
| N6 | После ошибки получить известный отказ либо unknown с блокировкой | Full no-effect/restored scope либо terminal unknown/application hold; no inverse/retry после delete, поздние результаты/replay/blocked request и безопасная собственная очистка | Pure coordinator/SQLite/guard проверки есть; native fault-wrapper подготовлен, не запускался |

Положительная публичная цепочка объединяет N1–N4 на одной собственной модели.
Отрицательные случаи выполняются на отдельной fixture, чтобы ошибка не заменяла
положительный результат. Для неизвестного удаления original job/status/hold
сохраняются; закрытие контролей не превращает его в succeeded.
Сквозной B5 использует свою сохраняемую пластину и не требует удаления её основания.

## Готовая проверочная инфраструктура

`verifier_b2_public_contract.py` связывает exact public DTO с coherent SQLite
row/private digest. Mutation требует durable preparation того же контекста;
return дополнительно требует original committed suppression lineage. Digest
не восстанавливается из угаданных ancestor IDs. Read-only row допускает только
явный synthetic `mutation=None`, добавленный читателем журнала; остальные поля
сравниваются полностью. Scalar/rename используют отдельные независимые native
callbacks, их результат не подменяется suppression/deletion oracle.

`verifier_b2_observation_fault.py` предоставляет два ограниченных Python-fault
hooks для единственного native-владельца. `LeafNoEffectFault` останавливает
dispatch до native deletion bridge; actual domain обязан доказать весь исходный
scope и released guard. `LeafObservationFault` вызывает отказ только после
нормально завершённого реального bridge и полного surviving SKETCH snapshot;
pending/неполный native результат не переименовывается в controlled fault.
Отдельный dispatch counter обнаруживает запрещённую повторную попытку, которую
сам hook блокирует. Helper не даёт cleanup/reconciliation authority и не вызывает
COM, пока native-владелец не подключил его к своей actual fixture.

Fault-helper: **12 pure passed /4,43 с** с actual JobRunner/MutationCoordinator/
SQLite и изменяемыми искусственными native-состояниями. Public contract:
**152 pure /27,43 с**; B2 native ledger ограничен32 событиями, невозможные34
согласованные строки отвергаются. Native fault-wrapper: **55 pure /40,37 с**.
Его passive gate требует точный positive report SHA, fixed helper manifests,
parent report и actual coherent SQL; следующий native до этого не запускается.
Unknown остаётся unknown/unresolved после собственной очистки, reconciliation
не выполняется. Pending/частичные данные запрещают cleanup/flag reset/retry.

Объединённый source helper-набор: **239 passed /78,17 с** — три новых helper
набора и прежняя positive оболочка. Это не CAD-приёмка и не повтор полного
package-набора. На этом этапе native fault-wrapper не запускался.
Package, установленный wheel и helpers текущего live positive не меняются.

Для native fault-case обязательны current-epoch ownership и тот же exact wheel;
до собственной очистки — terminal job, нормально завершённые CAD-вызовы,
полный журнал/receipt без pending, два независимых full current состояния,
точный surviving sketch/PID, old raw PID и сохранность neighbors/UI/files.
Если хотя бы одно условие не доказано, процесс удерживает STA/evidence и не
повторяет мутацию или CloseDoc. Известный controlled Python fault после native
return не является искусственно объявленным COM исключением.

## Оставшиеся задачи

Подготовка N5 выполняется без обращения к занятому SolidWorks. Пассивный
`verifier_b2_impact_refusal.py` связывает failed read-only preview с точным
request/document/configuration/object, public DTO и actual SQL digest. Проверяет
сохранность всех прежних jobs, отсутствие mutation checkpoint, точный отказ
`leaf_deletion_unsupported` либо `first_save_snapshot_unsupported`, а также replay
того же job без новых строк. **22 pure passed /0,70 с**, реальные SQLite jobs
искусственного сценария; native не запускался. Этот helper не удостоверяет
отсутствие CAD-эффекта и не разрешает cleanup.

Дополнительная дочерняя плоскость или непустые уравнения находятся вне текущего
полного BASE/first-save oracle. Для их native-отказов нужен отдельный полный
текущий collector; original BASE snapshot не заменяет наблюдение изменённой
fixture. N5 остаётся открытым до независимых before/after, защиты соседей и
подтверждённой собственной очистки. Произвольное удаление графа остаётся D2-DELETION.

`verifier_b2_impact_fixture.py` готовит три отдельные одноразовые own fixtures:
дочернюю плоскость на геометрически выбранной торцевой грани исходного extrusion,
неиспользуемую глобальную величину и её связь с частным файлом уравнений. Перед
изменением проверяет исходный registry/epoch/PID/canonical membership; плоскость
связывается с normally returned native handle и двусторонними parent/child
отношениями. Возвращённый неполный результат или потеря durable acknowledgement
не разрешают повтор/восстановление. Этот helper не подключён к текущему native.
Совместные fixture/refusal tests: **77 pure passed /4,55 с**. Доменные fixtures
используют искусственные native handles и реальный SQLite; CAD-приёмка не заявлена.

Следующий слой N5 подготовлен в `verifier_b2_impact_target.py` и
`verifier_b2_impact_ancillary.py`. Retained target collector создаётся до fixture
и читает текущие feature/body/dimension incarnations, anchors, BREP, эскиз,
плоскости, extrusion, controls и dependency/equation context под native watch.
Ancillary collector повторно использует установленные getters свойств,
конфигурации, annotations/views, материалов, units и creation controls.
Недоступные данные отклоняются по конкретному полю; baseline не подставляется.
Первая версия collector отклоняла четвёртый dimension плоскости. Совместные
четыре helper-набора этой версии: **158 pure passed /7,61 с**.
Перед native N5 ещё нужны полный session/neighbor/file census, сравнение
до/после фактического отказа, terminal fixture journal и безопасная очистка.
Текущий installed dev96 и его работающий positive driver не изменены.

Текущая версия дополнительно удерживает optional dimension только исходной
normally acknowledged дочерней плоскости: canonical owner/PID, первичный anchor
и текущая размерная запись должны совпадать. Для четырёх размеров отдельный
`verifier_b2_impact_views.py` связывает все current displays/slots/annotations/views
с теми же actual native DIM; лишний/заменённый объект не игнорируется. Исходные
три размера используют прежний installed view getter. Непустые/неизвестные views
по-прежнему являются explicit collector gate.

`verifier_b2_impact_session.py` объединяет target с полным native session census
и двумя полными снимками исходного соседнего BASE. Для linked equation отдельно
проверяет явную связь с частным fixture-файлом, его identity/timestamps/bytes/SHA;
файл не считается отсутствующим при пропущенном наблюдении. Before/after
сравниваются целиком. **232 related pure passed /12,01 с**, без CAD. Остаются
event envelope через сам отказ запроса, actual durable preview/execute/replay,
terminal fixture journal и собственная очистка в native driver. Эти исходные
проверки не являются N5/B2 приёмкой; текущий positive manifest не изменён.

1. Независимая инспекция/own cleanup завершены, baseline восстановлен и прежний
   процесс остановлен. Выполнить guarded positive с новой fixture; прежний failed
   event envelope сохранить. Причина не установлена; commit/replay и отдельная
   cleanup не заменяют positive gate.
2. Выполнить finite native fault/prewrite блок на exact dev96; dependent/linked
   CAD-случаи остаются обязательными видимыми требованиями N5.
3. После принятых внутренних gates выполнить подготовленную supervised MCP
   цепочку N1–N4 с actual scalar/rename и независимым observer на том же wheel.
4. Свести все шесть условий и оставшиеся ограничения. Пока доказательств нет,
   B2, B3–B5 и стадия1 не закрываются; CI не заменяет эту приёмку.

Публичный driver поверх B1 bootstrap, independent observer, predicates N1/N2,
canonical/HWND mapper и exact positive/fault SQL preflight подготовлены.
Итоговый related source-набор **694 passed /101,58 с** не вызывал SolidWorks.
Mapped observation hashes выводятся из actual metadata/counter; raw обоих
namespaces сохраняются, server counters/revisions не подставляются.
В установленном интерпретаторе failed positive был фактически отвергнут
preflight до metadata provider/CAD, без создания server. Это expected refusal,
не public native-приёмка; её статус **not_run**. Изменение annotation position/text,
для которого нет полного owner-bound правила, является отказом, а не успехом.
