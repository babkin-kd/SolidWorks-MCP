# Конечная приёмка B2 на dev96

B2 остаётся открытым. Привязка кандидата, full pure8427/323 и installed83/27 —
[контрольная точка](CHECKPOINT_DEV96.md). Результат positive suppression/return
dev95 сохранён отдельно; он не принимается за результат dev96.

| Условие B2 | Пользовательский результат | Требуемое доказательство на dev96 | Текущий статус |
| --- | --- | --- | --- |
| N1 | Driving depth10→12 мм, объём8000→9600 мм³ | Публичный dimension ID/revision/request; actual scalar readback, rebuild и полный независимый BASE, включая соседнюю модель | Ещё не принято на dev96 |
| N2 | Русское имя элемента; прежняя адресная ссылка действует | Public rename/readback, прежний object ID и PID/canonical membership; полные данные отличаются только разрешённым именем | Ещё не принято на dev96 |
| N3 | Подавить и вернуть собственное основание | Public suppression/return с original ownership, full bodyless/BASE snapshots, исходный sketch/DIMs/PID и имя тела; checkpoint/guards/replay | Dev95 positive принят; dev96 ещё не принят |
| N4 | Preview точного own leaf, затем удалить только основание | Read-only prepare, full BASE→SKETCH, exact deleted ID, preserved sketch, actual raw old PID1/4+null, удалённый ID отвергается при чтении; SQL/replay | Fresh guarded internal positive dev96 принят2/2, independent target/neighbor и cleanup/baseline подтверждены; публичная цепочка ещё не принята. Первый failed отчёт сохранён |
| N5 | Безопасный отказ для stale/foreign/dependent/linked/неполного scope | No-write/known-no-effect evidence реальных refused jobs; полный снимок, отсутствие native dispatch/checkpoint где применимо; unsupported CAD cases видимы отдельно | Stale/foreign actual native приняты в finite faults; `child_plane` выполняется, два equation cases ещё not_run; N5 целиком открыт |
| N6 | После ошибки получить известный отказ либо unknown с блокировкой | Full no-effect/restored scope либо terminal unknown/application hold; no inverse/retry после delete, поздние результаты/replay/blocked request и безопасная собственная очистка | Finite native fault-wrapper принят5/5,9137,84 с; root audit SQL/current baseline/cleanup принят. Historical unknown/unresolved сохранён; общий late/restart/reconciliation B4 gate остаётся отдельно |

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

**N5 native driver подготовлен.** `scripts/verify_b2_impact_native.py` запускает
один explicit `--fixture-kind child_plane|unused_equation|linked_equation` на fresh
private state с exact positive2 report/SHA и wheel96. Оригинальный B1 owner,
BASE preparation, fixture checkpoint/paired ledger и полный current session
предшествуют setup commit; preview/delete/replay batch проверяется под watches.
Terminal acceptance относится только к одному N5 case с own cleanup/исходным
empty baseline/non-STL preferences, не к whole B2/public.

Current neighbor сохраняет все данные rectangle capture; проекция к parent
first-save удаляет только два документированных добавленных поля для сравнения.
Controls/view bindings остаются в отчёте. Missing data не заполняется baseline.
Совместные девять наборов: **367 pure passed /79,97 с**, без CAD. Actual installed
negative preflight с failed positive1 дал ожидаемый отказ до COM: live=False,
owned=[], no creation returns/no jobs.sqlite. Metadata-only SDK запускался,
модели не создавались. Это проверка gate, не N5 native acceptance.

После terminal fault96 и принятой cleanup последовательно выполнить три fresh
прогона: `child_plane`, `unused_equation`, `linked_equation`. Replay идёт внутри
одной fixture; ошибка/pending удерживает STA и запрещает следующую case.
Только принятые три отчёта закрывают dependent/linked часть N5. `child_plane`
запущен после terminal faults/root audit; остальные два пока not_run.

**Finite faults dev96 принят.** Оба owner/wrapper завершились штатно exit0:
пять случаев stale, foreign, no-effect, controlled observation unknown и blocked
new request. Все196 captures normally returned; parent cleanup и original
baseline подтверждены. Root отдельно проверил SQL9 jobs, точный wheel/22 helpers,
пустую current CAD-сессию/CIPFalse и non-STL preferences. Report SHA256:
`b7f53667c2978685c5e1c689a8ba697645433ae30d46402cf0b45bb4415e6d74`.
Единственный historical unknown остаётся unresolved/reconciliation=None;
проверка не изменяет статус задания. Это конечный internal faults gate,
не public B2, не весь B4 и не завершение стадии1.

**Installed public prerequisite-only preflight принят** после terminal faults:
actual positive/fault reports и coherent SQL, текущие fixed helper hashes,
installed wheel и metadata-only SDK83 tools/27 mutations. Отдельная fresh state
не содержит CAD jobs.sqlite; native connection/модели не создавались.
`prerequisite_gate_verified=True`, но `native_b2_accepted=False` и
`public_mcp_accepted=False`. N5 dependent/linked gate остаётся открыт;
перед actual public run preflight повторяется на его собственной fresh state.

**Guarded positive dev96 принят.** Fresh прогон завершился за **4136,97 с**:
leaf2/2, parent4/4, все112 captures normally returned. Root отдельно проверил
actual report SHA, неизменные11 helpers, exact installed wheel, coherent SQL и
текущий native baseline. Все6 jobs succeeded,3 mutations committed;14 парных
leaf events, replay того же job. Independent SKETCH/neighbor подтверждены,
original creation receipts/jobs сохранены. Own cleanup принята, текущая сессия
пуста/CIPFalse; application/non-STL preferences совпали с оригиналом. Failed
positive1 и его отдельная cleanup остаются историей; B2/public/stage1 открыты.

N5 internal batch подготовлен: реальные JobRunner/MutationCoordinator/SQL
проверяют preview, replay, bypass-preview delete и replay на одной fixture.
Ошибки требуют реального `requires_reconciliation=False`; прежний тест вручную
созданной двухполевой ошибки исправлен. Два full session captures и watches обеих
моделей охватывают все четыре запроса, включая ABA, без второй fixture ради
replay. **331 related pure passed /26,56 с**, native N5 ещё не запускался.
Exact-wheel CLI и terminal fixture cleanup продолжают готовиться.

Current target reference census N5 дополнен всеми engineering feature PID,
body PID и полным набором current face/edge PID через установленный `_topology`
getter. Количество bindings должно совпадать с фактически захваченным BREP;
пропущенная topology не заменяется отсутствующим массивом. **80 related pure
passed /11,31 с** после этой правки, включая target/internal/session. При отдельном
запуске выявлена зависимость lazy import от pytest collection; helper dependency
перенесена в явный module import. Live fault helpers/package не менялись.

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
   процесс остановлен. Fresh guarded positive принят; прежний failed event
   envelope сохранён. Его исходная причина не доказана; новый положительный
   прогон не переписывает старый результат.
2. Завершить запущенный finite native fault/prewrite блок на exact dev96; dependent/linked
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

### N5: первая actual попытка и подготовка исправления

Первая `child_plane` попытка dev96 завершилась failed после пяти нормально
вернувшихся операций: проверка canonical identity новой плоскости отказала.
Переименование и preview/delete запросы не выполнялись. Setup сохраняется
unknown/unresolved без reconciliation и повторного исполнения старого запроса.
Независимая инспекция подтвердила quiescence и собственные модели. Две детали
закрыты без сохранения; отдельный read-only аудит подтвердил исходный полный
baseline, пустую сессию/CIPFalse, non-STL настройки и неизменный журнал.

Подготовлен binder normally returned plane: actual QueryInterface/каноническое
сравнение с единственной новой операцией до clear/rebuild. Переход к IRefPlane
разрешён только по exact E_NOINTERFACE; чужой IFeature или неизвестный HRESULT
не допускает fallback. Полный исходный ordered census сохраняется. Исправлена
проверка terminal baseline: проверяется полный composite snapshot с пустыми
document/window rosters, а не пустой список доказательств. **42 связанных pure
теста прошли /0,22 с**; native-причина старого отказа и новая N5 приёмка остаются
открытыми. Installed dev96/wheel не изменён.

Дополнительно **48 target +208 observer/refusal pure** прошли /4,95 и14,66 с.
Исправление четырёх CI test-fixture файлов проверено отдельно: **187 passed
/77,30 с**, pytest basetemp вне `work/`; production private-path guards и
negative outside-work случаи сохранены. Всего485 связанных pure-тестов;
общий full pure/CI после этих изменений ещё не выполнялся. Ошибочный локальный
запуск с ACL-denied basetemp не засчитан и заменён указанными проверками.
