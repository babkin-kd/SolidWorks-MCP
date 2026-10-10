# Ход разработки

## 11.10.2026 — source-развёртка: полная геометрия, имя списка ещё требует исправления

Подготовлены flat geometry/fixed-face/revision primitives и усиленный read-only
native-reader. Новых pure87; связанный sheet-поднабор260 passed/1,84с, без заявления
о полном наборе/wheel. Каталог v2 не расширен: установленный dev61 остаётся40/13.
Source-probe1 отказал до FlatPattern write из-за exact mass comparison; probe2 —
stale/not_started до native execution из-за mass round-off в revision≈4e−13 мм³.
Оба собственных документа закрыты. Из хеша исключены только redundant mass/area,
все geometry/tree/drivers/native parameters/refs/control сохранены; численные
mass-проверки остаются отдельными обязательными постусловиями.

Probe3 после durable checkpoint/owning guard подтвердил реальную native flat
форму8/12/6 при W40/H20/L30/t2/r2/K.42: D≈56,4610615681 мм,
V≈3387,66369408585 мм³/A≈3733,50794035824 мм²; fixed-face X подтверждён полными
native углами/нормалью/current body. Обратное сворачивание вернуло точные исходные
BREP16/28/14 и размеры/K/эскиз. Однако CutListFolder сменил русское имя на Sheet<2>:
full_folded_state_restored=false, итоговая приёмка не заявляется. Имя тела ещё
нужно снимать/подтвердить. CAN тела меняется через rebuild; flat body.GetFeatures
добавляет exact TemplateFlatPattern, FixedFace PID/footprint меняется через merge.

Все4 source-задания terminal/committed, новые unknown отсутствуют; source scopes
означают только наблюдения геометрии/параметров, не принятую публичную операцию.
Guard released/selection preserved, свой документ закрыт, non-STL настройки и
пустой/free baseline подтверждены. Доказательства/primary API/оставшиеся шаги:
SHEET_FLAT_STATE.md; private reports work/native-flat-development-probe-1…3.
Следующий шаг — домен/MCP и сохранение русских имён по exact refs/membership,
затем полный pure и один итоговый same-wheel internal/public блок. Усиленный
reader пока прошёл искусственные тесты, не был частью native-probe3. Импорт/экспорт
отложены, все стадии открыты. GitHub push/CI и дополнительных агентов нет.

## 11.10.2026 — листовой L-профиль dev61 принят на точном wheel

После полного pure3284 passed /323 CAD deselected (37,83с) зафиксирован чистый
source4482037089f58f94aea21fed29f74975183595e3; wheel dev61 собран/установлен только
в dev-.venv, рабочая v1 сохранена. Installed metadata40 инструментов /13 мутаций.
SHA wheel a6ccbf941dea3890f7d70647bea7fc8d4d27e1c9be18e88e52c6e4909f021ddb;
source digest2e7b0c32e924f3f40e20e3ab8f25be9e196e940d968f67b0e5c45785161f3b38.

Internal native6 и public MCP6 passed/accepted=true на одном точном wheel без
source PYTHONPATH. Внутренний: short-leg/stale до записи, known failure →
failed/rolled_back с полным исходным empty-state, успешная folded-форма16/28/14,
параметры/native K=.42 и сохранение отдельного исходника. Публичный: настоящая
SDK/stdio цепочка, schema/catalog, успешный профиль, request_id без второго
документа/профиля; в журнале ровно одна sheet.create_l_profile. Все задания
terminal, новых unknown нет; internal3 committed/1 rolled_back, public3 committed.
V≈3402,74333882308 мм³/A≈3749,59289474462 мм². Оба fixtures_closed=true;
guard/selection/non-STL настройки и пустой/free baseline восстановлены.

Контракт/ограничения и приватные протоколы перечислены в SHEET_PROFILE.md;
source unknown-probe4 сохраняется отдельно, не переписан успехом probe5/приёмки.
Принят один инженерный блок2.2, native-развёртка/прочие листовые операции ещё
не реализованы в v2. Все стадии открыты; импорт/экспорт отложены. Следующий блок —
native-развёртка собственного профиля без экспорта. Изменения и коммиты накоплены
локально; GitHub push/CI и дополнительные агенты не запускались.

## 11.10.2026 — кандидат dev61: домен/MCP и проверенное source-восстановление

Подключены sheet_prepare_l_profile/sheet_create_l_profile, общий runtime/STA и
каталог40 инструментов /13 мутаций. Явный K-фактор обязателен, русские имена
сохраняются. Полная ревизия, durable checkpoint, парные закрывающие capture,
полный BREP/native allowance/собственные driving-размеры и точный bundle
проверяются до объявления успеха. Partial/unproved создание остаётся unknown.

Source-probe4 сохранил unknown после известного сбоя: native удаление absorbed
bundle оставило единственный собственный разабсорбированный эскиз. После
терминальных вызовов контрольная модель закрыта по доказанному владению;
исходный журнал не переписан. Восстановление усилено отдельным удалением только
этого профиля после повторного полного доказательства PID/CAN/snapshot,
размерных владельцев, baseline, отсутствия тела/чужих узлов/зависимостей.
Source-probe5 подтвердил failed/rolled_back и весь исходный empty-state;
собственная модель закрыта, session/guard восстановлены. Это source-проверка,
не приёмка установленного wheel. Внутренний и MCP sheet-only harness готовы;
импорт/экспорт не включены, все стадии PLAN.md открыты. Новый wheel пока не принят.

## 11.10.2026 — source-прототип листового профиля, выпуск ещё не принят

Начат инженерный блок 2.2: открытый L-эскиз → реальное листовое основание с одним
сгибом 90°. Обязательны явные размеры и K-фактор; .42 использован как явный
параметр контрольного примера, не как корпоративный профиль или значение по
умолчанию. Полное тело проверяется независимо от массы: 16 вершин,28 рёбер,
14 граней, включая четыре шва на торцах, четыре конечных дуги,12 плоских граней
и внутреннюю/наружную цилиндрические стенки. Полный двухлинейный эскиз, пять
отношений и два собственных driving-размера проверяются отдельно.

Первая development-проба получила unknown: ожидавшийся минимальный BREP
16/24/10 не учитывал native-швы листового сгиба. Terminal read-only аудит
сохранил исходный журнал, затем единственная доказанно собственная несохранённая
деталь закрыта. Сам пробник также исправлен: DocumentCatalog.close освобождает
адаптер, поэтому очистка собственных документов должна предшествовать ему.
Native-probe2 подтвердил полный BREP и параметры; probe3 — также точные связи,
референсы и русские имена вспомогательных узлов/размера длины. Каждая новая
проба создавала свой документ после проверки пустой/free сессии; собственные
модели закрыты после терминальных вызовов, guard/selection/non-STL настройки
сохранены. Native V3402,743338823081 мм³ /A3749,5928947446205 мм².

Обнаружена отдельная особенность SW2023: PID FoldUpDownSketchFolder разрешается
в другой объект. Для этой роли реализована явная проверка точного retained
handle через владельца FlatPattern и полный native absorption traversal;
неверная ссылка не принимается и не используется. Suppressed own-features
проверяются через статус2 и exact native identity; общий resolver не ослаблен.
Владение выводится из body membership, документированных folder getters,
absorption и принадлежности cut-list телу. Отличия дерева лишь обнаруживают
остаточные чужие изменения. Имена не устанавливают владение.

Проверки: общий pure-набор после расширения reader —3194 passed /323 CAD
deselected,36,16с; после добавления receipt/ownership/naming —108 связанных
тестов passed,0,38с. Это искусственные domain/native-shaped проверки.
Development native-пробы используют исходники и **не являются** установленной
same-wheel или public MCP приёмкой. Скрипты, CAD-данные и журналы приватные:
`work/native-sheet-development-probe-{1,2,3}/`,
`work/pure-sheet-development-final.log`.

Подготовлен adapter для построения, доказательства владения, native evidence и
scoped deletion; deletion пока не проверен в CAD. Доменная mutation и MCP-фасад
ещё не подключены. Принятый dev60/v1 не переустановлены, каталог38/12 сохраняется.
Следующий шаг — завершить домен/фасад, затем собрать один итоговый wheel и пройти
его pure/metadata/internal/public приёмку. Развёртка/DXF, большой многотельный
листовой сценарий и стадии плана остаются открытыми. Один агент, без push/CI.
См. [SHEET_PROFILE.md](SHEET_PROFILE.md).

## 11.10.2026 — dev60: явное скругление принято через native и MCP

Принят инженерный блок пункта 2.1: одно постоянное скругление полного ребра
прямоугольного основания, явные ссылки/радиус/русское имя, полный источник и
конечная дуга/цилиндрическая BREP, native definition и independent mass proof.
Каталог38 инструментов /12 мутаций; pure3111 passed /323 CAD deselected,
installed metadata принят. **Internal native7 /public MCP7 passed, оба accepted=true**.
R2: V7991,4159265358985 мм³, A2789,6991118430774 мм²,10/15/7; R1,5 после
внедрённого сбоя удалён только после полного own-definition/body proof. Исходный
эскиз/три размера, чужая контрольная модель с mark=7 и вид сохранены. Проверены
stale/material prewrite и request_id; свои документы закрыты, baseline пуст/free.

Dev59 failed/unknown сохранён. Native-пробник показал другую фазу базового
ICurve и семантику FilletItemsCount=-1 для постоянного радиуса. Dev60 использует
IEdge.Evaluate2 и документированный packed status, без неопределённого верхнего
слова в ревизии. После terminal read-only аудита полного BREP две собственные
unsaved детали dev59 закрыты по постоянному разрешению; unknown-журнал не изменён.

Источник wheel `0b8f214a18134b4e9281c01f8d8816df2bd3c9ba`,
SHA256 `fd77501a64a634bd5861458242aeea4da2cce6f8ea8406c7393840402814e7f0`,
digest `eef676ae2dbe1e446d7ba5a683784e8c9cd30cb140d96b70cfa9353333617d0e`.
Отчёты: `work/native-fillet-dev60-1/report.json`,
`work/native-fillet-mcp-dev60-1/report.json`, `work/metadata-dev60-1.report.json`.
Приблизительно internal5м52с /public2м33с; pure36,11с; failed59 отдельно3м53с.
Контракт, границы native-покрытия и восстановление: [PART_FILLET.md](PART_FILLET.md).
Все стадии открыты, импорт/экспорт отложены. Один агент, локальные изменения,
без push/нового CI; v1 сохранена.

## 10.10.2026 — dev58: линейный массив принят через native и MCP

Завершён ограниченный инженерный блок нового native LPattern существующего
сквозного отверстия. Доменная часть и MCP-фасад включены в один итоговый wheel:
36 инструментов /11 мутаций. Pure3023 passed /323 CAD deselected, installed
metadata36 принят. **Internal native8 /public MCP9 passed, оба accepted=true**.

Проверены X3/шаг10 (V7151,7699835307585 мм³, A3195,8406743523146 мм²,8/18/9),
Y2/шаг6,5 с полной формой перед восстановлением, сохранение исходных эскизов/
шести размеров, stale/material prewrite, request_id, полные BREP и independent
native mass, диагностический circle native_id. Persistent body round-trip выдержал
реальный AccessSelections rollback. Свои документы закрыты, baseline пуст/free.

Источник wheel `a03e40bc533d889aa85c5dd32535b1bc40e249b3`, SHA256 `88260b523c9cb386eb2d0eef4b74fda9105bd9ab86dba2a095beb8759a19912e`,
digest `c2f71e0cafaa1e3ad927d6d69e06cb404f3541902f73e63654d02ac07244eec2`.
Отчёты: `work/native-pattern-dev58-1/report.json`,
`work/native-pattern-mcp-dev58-1/report.json`; контракт [PART_PATTERN.md](PART_PATTERN.md).
Dev57 остаётся непринятым, его unknown/journal и аудит очистки сохранены.
Все стадии открыты; импорт/экспорт отложены. Один агент, без push/CI.


## 10.10.2026 — массив отверстий: dev57 не принят, исправление dev58

Доменная операция, native-адаптер и MCP-фасад одномерного массива подготовлены
до wheel. Dev57: pure3020 passed /323 CAD deselected, metadata36/11 принят.
Native дошёл до шести завершённых сценариев и создал массив, но AccessSelections
заменил IBody2 после rollback; сравнение с прежним CAN остановило restoration,
задание осталось unknown. Приёмка=false, журнал не изменялся.

После завершения helper read-only аудит подтвердил terminal jobs, durable NewDocument
ownership обеих деталей, полную ожидаемую форму X3/шаг10, исходные эскизы/дерево,
free CommandInProgress=False и оба blocking_state=0. Собственные документы закрыты
по постоянному разрешению пользователя, baseline снова пуст/free. Отчёт и аудит:
`work/native-pattern-dev57-1/report.json`, `cleanup-audit.json`.

Кандидат dev58 заменяет проверку прежней COM-обёртки на строгий persistent body
round-trip/current membership/IsSamePersistentID, сохраняя полную BREP-проверку.
25 связанных pure прошли, полный набор и native-приёмка выполняются. В native
known-failure сценарии проверяется Y2/шаг6,5 с полным восстановлением исходного
отверстия; основной успешный сценарий X3/шаг10. Стадии остаются открыты,
импорт/экспорт отложены. Работа одним агентом, без push/CI.


## 10.10.2026 — dev56: размеры существующего отверстия

Реализован один инженерный блок: явные основание/круглый эскиз/размер → подготовка
нового X/Y/диаметра → durable checkpoint → запись единственного собственного
драйвера → rebuild и полная BREP/constraint/native-mass проверка. Новые инструменты
`part_prepare_hole_dimension_change` и `part_set_hole_dimension`, каталог34/10.
Известный решённый собственный эффект допускает точное scalar restoration;
чужие и нерешённые эффекты дают unknown/application hold, без повторения записи.

Полный pure-набор2940 passed /323 CAD deselected; installed metadata34 принят.
Пакет зафиксирован в Git `cbf532e06c6f98b9d301314186c8e87a04e12383`:
wheel SHA256 `ad254287d061eb5f5ac7a42d24e5d1708610d13627f8f01ae32df2283ad87bf3`,
source digest `49b8c3a3d52c8cd84f1d2875581caf6fad154e849039236d7bd0be3b2a825328`.
Первый native-прогон не принят: верификатор ошибочно требовал checkpoint у
отказа подготовки вне материала. Задание корректно failed/hole_outside_material,
без native-записи и checkpoint. Собственные детали закрыты и флаг восстановлен.
Исправление верификатора проверено83 связанными тестами и итоговым pure-набором2940.
Wheel не менялся; повторный полный блок редактора имеет отдельную область и не
повторяет прежние проверки толщины/rename/busy. **Internal native10 принят**,
полная форма, исходный документ и пустой/free baseline подтверждены.

Первый public-прогон не принят: ToolSpec верификатора для dimension_list не
включал defaults limit=100/cursor="", из-за чего read-журнал не соответствовал
ожидаемой проекции. Само изменение диаметра succeeded/committed с released guard.
До завершения только своих зависших helper-процессов проверены все16 terminal
заданий, все guard, live roster, полная геометрия и stamp контрольной детали.
Модели закрыты по постоянному разрешению пользователя; журнал не переписан,
failed-отчёт и отдельный protocol-audit сохранены в private work/.
Исправление проверено50 связанными тестами и итоговым pure-набором2940 /323 CAD
deselected. **Свежий public-прогон9 принят** на том же wheel; создание детали/
пластины/отверстия, изменение Ø6→Ø8, оба повторных request_id, SDK-журнал,
сохранение исходного документа и окончательная очистка подтверждены.
Итоговая ограниченная приёмка dev56: metadata34/10, internal10, public9;
оба CAD-отчёта accepted=true. Report: `work/native-hole-edit-dev56-2/report.json`
и `work/native-hole-edit-mcp-dev56-2/report.json`. V7497,345175425634 мм³,
A2950,79644737231 мм², census8/14/7; пустой/free baseline восстановлен.
Обнаружено следующее исправление поля snapshot.native_id окружности: оно
перезаписывается ID periodic endpoint, при правильных key/canonical refs.
Драйверы и форма подтверждены; дефект диагностических данных внесён в пункт1.4
PLAN.md, требует исправления и проверки следующего установленного кандидата.
Рабочая v1 сохранена; один агент, без push/CI, импорт/экспорт отложены, стадии открыты.

## 10.10.2026 — dev55: guard и MCP-ускорение приняты

Установленный **dev55** принят в ограниченной инженерной цепочке новая деталь → пластина40 × 20 × 10 мм → Ø6 при X=10/Y=10. **2906 pure passed, 323 CAD deselected; metadata32 tools; internal native10 / public MCP stdio7 passed, оба accepted=true** на одном точном wheel. Общий guard проверен также на толщине12→10, русском rename, busy-отказе, stale и scoped restoration после намеренного сбоя. Собственные контрольные документы закрыты, CommandInProgress восстановлен, сессия пуста/free. Новых инструментов нет: каталог32/9; рабочая v1 и исторические wheel сохранены. Стадии открыты.

Артефакт: Git `4ebe1a93a5d846b670a4381fae1fb8c56d0cbb0b`, SHA256 `1e69033d942f108aaeb826c8c36d08de96bbf2a15b047fa38a499e8d6d6cf4de`, source digest `27099c06b58e64fe0470fb8a69868d871efbe66dda3564bf63293b93c6ed6099`. Native internal принят только третий свежий прогон; первые два accepted=false сохранены с причиной verifier-сбоев. Исправления helpers/record не меняли пакет wheel. Ускорение подтверждено по одинаковой public-цепочке: пластина69,560→31,512 с, отверстие134,477→51,249 с; сумма длительностей заданий281,146→159,219 с, около43,4% меньше. Это queue-inclusive job times одного сопоставимого прогона, не гарантированное ускорение любых моделей и не полное wall-clock время. Подготовительные чтения не ускорены, два полных снимка и durable протокол сохранены. См. [ENGINEERING_BENCHMARKS.md](ENGINEERING_BENCHMARKS.md). Следующий инженерный блок2.1 — изменение независимых параметров уже созданного отверстия с проверкой границы/формы/восстановления. Пункт1.5 полностью не закрыт. Без push/CI и дополнительных агентов.

## 10.10.2026 — dev55: защищённый CommandInProgress для model-мутаций

Короткий последовательный ABBA-замер установленного dev54 на temporary kernel-теле локализовал задержку полного BREP: около7,2 с при False и0,38–0,40 с при True в обоих STA, 1177 явно подсчитанных reader calls, точные снимки одинаковы. Документы не создавались; свой флаг восстановлен. Кандидат dev55 переиспользует существующий ApplicationDocumentGuard для явных model-мутаций с отдельным evidence scope application_model_mutation_guard_v1. Активация только после durable checkpoint; busy не заимствуется, uncertain release сохраняет общий hold. Подготовительные чтения флаг пока не меняют. Связанные guard/SQLite/lifecycle проверки:64 passed. Internal harness снял общий флаг, чтобы проверять production lifecycle; в той же контрольной детали добавлены размеры12→10, русское переименование и busy rejection. Полный pure/wheel/native впереди. Историческая приёмка dev54 сохранена; стадии открыты, один агент, без push/CI.

## 10.10.2026 — dev54: отверстие принято через installed MCP

Принят ограниченный сценарий **dev54: новая деталь → пластина 40 × 20 × 10 мм → сквозное отверстие Ø6 мм, X=10/Y=10 мм**. Полный pure-набор: **2885 passed, 323 CAD deselected**. Установленный wheel: metadata32 tools, **internal native6 passed / public MCP stdio7 passed**, оба accepted=true. Проверены stale до записи, восстановление после известного сбоя, повтор request_id без второго документа/отверстия, полная геометрия и сохранение исходного документа. Собственные контрольные детали закрыты; пустая/free сессия восстановлена. Каталог — 32 tools/9 mutations. Рабочая v1 не изменена; прежние wheel сохранены. Стадии остаются открытыми.

Артефакт зафиксирован на Git `6e89b2389390290f36e6d2c039fb62b6ffebdd64`, SHA256 `cf53edb40e6a75711421874ce67144e6a4cc03f2feee6c35b137bdcf78d64268`. Установленные внутренний и public отчёты совпадают по wheel/source digest; пропущенные CAD pytest не засчитаны. Измерены времена заданий, выявлена разница internal/MCP, причина ещё не доказана. См. [PART_HOLE.md](PART_HOLE.md) и [ENGINEERING_BENCHMARKS.md](ENGINEERING_BENCHMARKS.md). Документация не требует повторной CAD-приёмки. Локальные коммиты, без push/CI и дополнительных агентов.

## 10.10.2026 — dev54: исправление native полного круга

Dev53 установлен только в dev-окружение и прошёл metadata (32 tools). Первый internal native дошёл до реального отверстия и выявил неподтверждённое восстановление: unknown сохранён, повтор не выполнялся. Read-only диагностика выявила periodic endpoint handles Type=-1/Status=1 и отдельный diameter relation type15. Dev54 сохраняет точные persistent/reference/owner/geometry proof этих служебных handles отдельно от перечисляемых точек; линейный scope отрицательные точки по-прежнему отвергает. Добавлены регрессионные проверки. Собственные два документа доказанно идентифицированы и закрыты после терминального вызова, флаг освобождён, пустой/free baseline подтверждён. Подробности: [PART_HOLE.md](PART_HOLE.md). На момент исходного checkpoint новый wheel/native был впереди; итоговая приёмка описана выше.

# История локальных проверок первой стадии

## 10.10.2026 — dev53: исходный сценарий отверстия и MCP-фасады

Подготовлены полный circle reader с LONG IsCircle, точными curve/radius/normal/rotation и всем constraint network; независимый X/Y/diameter classifier, persistent binder/plane/origin proof; domain/native through-all cut/restore на общем проверяемом протоколе углового выреза. Подключены `part_prepare_through_hole`/`part_create_through_hole`, lazy owning-STA runtime и освобождение references. Исходный каталог32/9 mutations, scope `single_base_circular_through_hole_v1`; census8/14/7 выбирает полный reader и не заменяет его.

**2875 pure passed, 323 CAD deselected**. Первый полный прогон: 2874 passed/1 failed из-за версии Registry-шаблона; после исправления итоговый прошёл. Circle/linear/binder/sketch/constraints связанный набор222 passed; domain/SQLite commit/stale/request_id/rollback/unknown/foreign проверены искусственно; MCP/metadata/verifier gates58 passed. Подготовлены internal/public installed-wheel верификаторы с V/A/полным census и SDK job-tracking preflight. На момент исходного checkpoint native-приёмка ещё не запускалась; последующий фактический отказ и очистка описаны выше. Исторические результаты не засчитываются за dev53. Один агент, без push/CI, стадии открыты.

## 10.10.2026 — отверстие: исходные BREP и инженерные постусловия

После принятого dev52 продолжена цепочка «пластина → одно сквозное круглое отверстие». Подготовлены полный planar/cylinder BREP-reader и `ThroughHole`: явные ссылки, X/Y/диаметр, русские имена, minimum material margin 0,001 мм. Shape matcher проверяет полную конкретную границу; массы/census недостаточно. Исходники пока не подключены к каталогу; установленный dev52 и 30 tools/8 mutations сохранены.

Связанные **422 pure passed**: новый BREP/domain, planar/cylinder, cut preparation, revolve domain. Предыдущий sandbox запуск дал 407 passed/15 setup errors из-за доступа к pytest temp; повтор с доступом к temp прошёл полностью. Полный набор/новый wheel для незавершённого блока ещё не запускались.

Temporary-kernel source probe на реальном SolidWorks: точные парные снимки для одной и двух Ø6 в пластине 40×20×10, второе тело перенесено; 8/14/7 и 8/16/8, независимые native V≈7717,256661 и 7434,513322 мм³, A≈2931,946891 и 3063,893783 мм². Документы не создавались/редактировались/сохранялись; пустая сессия/свободный флаг сохранены, процесс завершён. Source SHA256 `376c9bc705b5186b880432541068de2b63de64e81b991227abbd0a217eb27e90`; после пробника pure-проверками усилен closing stamp type. Это **не installed-wheel/native-приёмка CAD-операции или MCP**.

Далее: полный circle sketch/три driving dimensions → native cut/scoped restoration → domain/MCP фасад → полный pure и итоговый installed-wheel acceptance. Импорт/экспорт отложены, стадии открыты. Один агент, без push/CI. См. [PART_HOLE.md](PART_HOLE.md).

## 10.10.2026 — dev52: полное вращение основания принято на installed wheel

Установленный **dev52** принят для цепочки «новая деталь → полное вращение прямоугольного профиля, радиус 10 мм, высота 30 мм»: **2521 pure passed, 323 CAD deselected; fresh same-wheel internal 5 native passed и public MCP stdio 7 native passed, оба accepted=true**. Каталог — **30 инструментов, 8 mutations**. Подтверждены полностью определённый собственный профиль и ось, полный цилиндрический BREP (0 вершин, 2 замкнутых круговых ребра, 3 грани), независимые native объём около 9424,777961 мм³ и площадь 2513,274123 мм², stale-отказ до записи, scoped restoration после реального создания вращения и повтор request_id без второй операции. Исходная деталь, выделение/marks, вид и non-STL настройки сохранены; свои модели закрыты, сессия свободна. Приёмка ограничена этой цепочкой: исторические проверки других scope не засчитываются за новые прогоны dev52. Импорт/экспорт отложены; стадии плана остаются открытыми.

Собственная ось подтверждается native reference/owner/geometry/selection, профиль — всей сетью семи ограничений и двумя driving dimensions. Full periodic BREP, отдельная native масса, third angular dimension и исходный baseline проверяются до committed; artificial unknown/foreign cases не удаляются и не повторяются. Кандидат разработан одним агентом; пакет накоплен/проверен локально, без push/Actions. Новое дополнение PLAN.md 1.5 про измерения производительности сохранено; диагностика ещё не объявляется в API. Документация: [PART_REVOLVE.md](PART_REVOLVE.md). Wheel SHA `de434cd5b72206077c49e096744c2d822019242ea17bf213bd57c604c97b5080`, clean package commit `db37a33e400a190a5ae116f2f09b4d56fd70e751`; исходная v1 не менялась.

Исторические результаты относятся только к указанным сборкам и scope; они не переносятся на новые кандидаты. Текущий план: [PLAN.md](../PLAN.md).

**Сквозной угловой вырез, dev50–dev51 (10.10.2026).** Историческая приёмка dev51 для цепочки «новая деталь → пластина 40 × 20 × 10 мм → сквозной угловой вырез 10 × 5 мм»: **2426 pure passed, 323 CAD deselected; fresh same-wheel internal 6 native passed и public MCP stdio 7 native passed, оба accepted=true**. Каталог — **28 инструментов, 7 mutations**. Подтверждены полный L-образный BREP (12 вершин, 18 рёбер, 8 граней), независимые native объём около 7500 мм³ и площадь 2700 мм², internal stale-отказ и scoped restoration после настоящего создания выреза, публичный повтор request_id без второй операции и сохранность исходной детали/выделения/вида. Свои модели закрыты, флаг свободен, non-STL настройки сохранены. Это ограниченная приёмка указанной цепочки; исторические проверки других scope не засчитываются за новые прогоны dev51. Импорт/экспорт отложены, стадия 1 открыта.

Dev50 failed/unknown сохранён: фактический вырез имел тип ICE, прежняя проверка только Cut не разрешила восстановление после инъекции. Read-only audit подтвердил полный ожидаемый L-профиль; после terminal-процесса закрыты только свои два unsaved документа, освобождён свой флаг. Bookkeeping после неподдерживаемого JobStore context manager завершён отдельным read-only подтверждением пустой свободной сессии; исторический job не повторялся и остаётся unknown, mutation reconciled, исходный native отчёт accepted=false. Приватные свидетельства: `work/native-cut-dev50-1/report.json`, `work/native-cut50-audit/report.json`, `work/native-cut-dev50-1/cleanup-audit.json`. В dev51 ICE допускается только при native underlying Cut у точного собственного handle; pure-проверка исключает ICE/Boss.

Принятый wheel SHA256 `5726835b43b00d588ecae7fb2413a2e8485b04bc0c32698826c63fc897cda549`, Git `ec94b8eb539d06c549375458ee37e9d85710ac82`, source digest `96363aeca9d068eb8778290427e4e7a20dd12fab60fceef751fb01d0d7fc1fb5`. Свежие отчёты: `work/native-cut-dev51-1/report.json` (6 cases) и `work/native-cut-mcp-dev51-1/report.json` (7 cases); verifier SHA256 `3dd4f0219255ab6d405f1f68ab92fa2107b08a8e80a09a15df498db836fce9e8` / `b0c2232cc8406798b88f45520ca0ba19aff42179c537abc35a91470daf091998`. 28 tools/7 mutations; исходная деталь, её mark7/вид и настройки сохранены. Следующие детали/вращение требуют новых контрактов и собственного установленного кандидата.

**Ускорение полного capture эскиза, dev49 (10.10.2026).** Повторные bindings канонических сущностей объединены только внутри одного снимка; в конце все уникальные persistent references заново разрешаются и проверяются. Проверки поздней подмены владельца, identity, координат, ID, типа и состояния сохраняются. Два полных capture и BREP не сокращены; новый CommandInProgress не устанавливается. **2380 pure passed, 323 CAD deselected**, fresh installed same-wheel internal 11 и public MCP 11 accepted. Публичная цепочка даёт объём `13500.000000000004` мм³; свои документы закрыты, флаг свободен, non-STL prefs сохранены.

Wheel SHA256 `8e0902128736038a407ba66042a1799c851aa744f1a3c70b468ae886e9ba6658`, Git `acac9e27a410b001861815b3d8abf8edc7809c5f`, source digest `cd2622a210a294b1883387195357a8afedaf09e53f03bea11dd50134dcce99ab`. Приватные отчёты: `work/native-sketch-dev49-1/report.json` и `work/native-sketch-mcp-dev49-1/report.json`; verifier SHA256 `227a1461304c6ac8eed3c9a096abeac16ae8349b80a1ba599b072c6a4e076938` и `635fabf656cabcacaeb974ace6633d2a8757bf98293db1060b4d421daf7d351a`. Metadata/stdio подтверждают 26 инструментов и 6 mutations. SQL elapsed в штатном CommandInProgress=False: get 38,64/41,68 с, prepare 40,88/41,75/42,18 с, width/height mutation 107,91/97,19 с; сопоставление с dev48 см. [SKETCHES.md](SKETCHES.md). Это измерение контрольной базы, не общий COM/RPC-бенчмарк.

**Следующий блок: угловой сквозной вырез.** В исходниках подготовлен отдельный внутренний read-only контракт с явными эскизом/плоскостью, двумя полными captures, ревизией и ожидаемой L-образной формой. 15 искусственных тестов приняты отдельно; writer, восстановление, MCP-фасад и native-приёмка ещё впереди. Новый модуль не входит в принятый wheel dev49. Рабочая v1 сохранена; push/CI/агенты не запускались.

**Эскизы и изменение ширины/высоты, dev42–dev48 (10.10.2026).** Реализованы полный bounded capture линейного плоского эскиза и отдельный контракт изменения независимых размеров прямоугольной базы. Actual model-origin definition отличается от внутренней проекции; Type2 11/12 определяет оси, GetType=2 их не различает. Native GetReferenceEntity/GetEntities могут возвращать alternate IUnknown при тех же persistent references; сущности разрешаются к текущим объектам с проверкой владельца/ID/геометрии. ISketchLine не наследует GetID/GetSketch/Status сегмента. GetRelations возвращает новые wrappers без PID: полная семантика всех связей проверяется по resolved entities и двум captures, временные wrappers не используются как долговечные identities.

Dev42–dev45 остановились на строгих read-only отказах до изменения размеров; свои модели/флаги очищены. Dev46 прошёл полное чтение и stale, но первая ширина привела к historical unknown: решатель вернул координату угла с несколькими ULP, точная классификация горизонтальности/побитовое восстановление были чрезмерно строгими. Отдельный read-only аудит подтвердил размеры 40/20/10 и прежнюю структуру связей; по делегированному пользователем решению закрыты только собственные unsaved control parts, освобождён собственный flag. Журнал сохранён: статус задания unknown, phase reconciled, resolution accept_current_state с доказательством пустой сессии после закрытия контрольных моделей; успех операции не объявлен. Failed-отчёты и аудит остаются в work/.

Dev47 уточнил ограниченный контракт восстановления: структура/контроли точны, точки 10⁻¹² м, вершины полного валидированного прямоугольного BREP 10⁻⁹ м, native volume/area rel 10⁻¹⁰ / abs 10⁻⁸ мм³/мм². **2350 pure passed/323 CAD deselected; installed internal 11 native passed, accepted=true**. Общий dimension_set_value сохраняет blocker эскизов.

Dev48 подключил три sketch tools; **2368 pure passed/323 CAD deselected**. Чистый wheel из `d3f1d64329b86aa4231db66881556624ed639834`, SHA256 `e5261f34dc91e59972edb7a916225d10e5064bfcac131522714efd8486fbe9ec`, source digest `53c24815ecba87f3da188d0969bc65be48b9230f9ece2c7f2f552392f5b3732e`. Artifact/installed metadata stdio принят: 26 tools, 6 mutations. **Fresh same-wheel internal 11 native passed + public MCP stdio 11 native passed, accepted=true**. MCP целиком создал документы/пластину, изменил width 45 / height 25 / thickness 12; независимый объём `13500.000000000004` мм³. Повтор request_id не повторяет ни NewDocument, ни setter; stale отвергнут до записи. Internal инъекция после фактических setter/rebuild/mass read подтвердила scoped restoration. Исходная деталь, выделение mark7, вид, геометрия и non-STL prefs сохранены; свои модели закрыты, flag свободен. Приватные отчёты: `work/native-sketch-dev48-1/report.json` и `work/native-sketch-mcp-dev48-1/report.json`; verifier SHA256 соответственно `227a1461304c6ac8eed3c9a096abeac16ae8349b80a1ba599b072c6a4e076938` и `635fabf656cabcacaeb974ace6633d2a8757bf98293db1060b4d421daf7d351a`.

В публичном штатном режиме CommandInProgress=False SQL timestamps показали около 54–55 с для complete get/prepare и 140–144 с для width/height mutation. Это elapsed job time, не число COM-вызовов. Ускорение полных captures включено в 1.4 без отмены проверок. Следующие инженерные операции — вырез/вращение и расширение эскизов. Рабочая v1 не менялась, импорт/экспорт не расширялись, push/CI/дополнительные агенты не запускались; стадия 1 открыта.

**Создание документа и полная первая инженерная цепочка, dev40/dev41 (10.10.2026).** Dev40 добавил внутренний `DocumentCreationCatalog` и exact returned-document receipt: настроенный `.prtdot` fingerprint, explicit application revision, checkpoint до флагов/Lock/NewDocument, собственный command flag, сохранение выделения/меток существующих деталей. Native-приёмка dev40: 6 сценариев приняты; собственные документы закрыты. Русские заголовок/конфигурация проверяются чтением, файл шаблона не меняется. Известный сбой закрывает только точный собственный новый unsaved part, восстанавливает прежнюю активацию; unknown/чужие документы не принимаются за собственные и не повторяются. Initial baseline — пустая сессия или открытые детали без редактируемого эскиза; исходные сборки/чертежи и другие шаблоны пока вне scope.

Dev41 зарегистрировал три инструмента: `document_list_templates`, `document_prepare_create_part`, `document_create_part`. Каталог **23**, пять реализованных mutations, scope нового документа `new_empty_part_document_v1`. Application ID отображается в durable context.document_id с configuration=""; настоящий новый doc_* возвращается в after.created_document_id. **2290 pure passed, 323 CAD deselected**; чистый installed wheel из `1fc8d4b85ffc80c9d67c895013eab74808dd773a`, SHA256 `2484a03453b09e0904b9dbd72d90d5c577d26c4171e508001f1712bada9db10f`, artifact/metadata stdio23 accepted. Fresh same-wheel internal **6 native passed** и public MCP stdio **6 native passed**, оба accepted=true. Первый документ в публичном тесте создал MCP; повтор request_id не создал второй. Второй документ также создан MCP с сохранением первого выделения/вида/геометрии. Пластина 40 × 20 × 10 мм затем получила толщину 12 мм, независимый объём `9600.000000000002` мм³. Свои модели закрыты, исходная пустая сессия восстановлена, command flag свободен, non-STL настройки сохранены. Приватные отчёты/верификаторы и ограничения — [PART_CREATION.md](PART_CREATION.md). Импорт/экспорт не проверялись; v1 сохранена, дополнительные агенты/push/CI не использовались. Следующий блок — геометрия/ограничения эскиза и ширина/высота; стадия 1 открыта.

**Инженерное построение и редактирование через MCP, dev39 (10.10.2026).** Пластина 40 × 20 × 10 мм с русскими именами и тремя размерами построена по явной плоскости/ревизии; полная BREP, объём/площадь, native constraints и scoped rollback проверены. Толщина изменена до 12 мм, независимый объём 9600 мм³. Исправлены обнаруженные native-дефекты: отсутствующий ISketch.GetFeature (dev36 unknown сохранён), потеря выделения при размерном перестроении (dev37 false). Dev38 сохранил выделение, используя временный список и свежие транзитные ISelectionMgr. Dev39: **2265 pure passed, 323 CAD deselected**, чистый wheel `89c832e`, offline artifact/installed metadata и 20 инструментов приняты. Same-wheel internal: **3 native passed**, public MCP stdio: **4 native passed**, оба accepted=true. Две остальные штатные плоскости отдельно прошли по 3 внутренних native-сценария. Все четыре запуска восстановили собственный флаг, закрыли контрольные детали, сохранили исходное выделение с меткой 7 и вторую деталь. Импорт/экспорт не проверялись; создание нового документа через MCP ещё не перенесено. Стадия 1 открыта. Подробная область и fingerprints: [PART_CREATION.md](PART_CREATION.md).

**Приоритетный инженерный сценарий, dev35 (10.10.2026).** Добавлена внутренняя подготовка пустой детали с явной постоянной ссылкой на плоскость, полным снимком размеров/управления/геометрии, трансформацией плоскости, русскими именами и аналитическими постусловиями пластины 40 × 20 × 10 мм. Полный стабильный набор: **2237 pure passed, 323 CAD deselected**. Чистый wheel `9fc6cca`, offline artifact и installed metadata/std io приняты; 18 публичных инструментов. Свежий installed native: **8 passed, accepted=true**, собственные детали закрыты, guard освобождён, независимые модели/выделение/вид и настройки вне STL сохранены. Первая попытка не принята: ошибка аргументов функции проверки настроек в верификаторе; исправление `b8729f3`, свежий отчёт отдельно. Принята только подготовка, построение и публикация не реализованы. Импорт/экспорт отложены, стадия 1 открыта. См. [PART_CREATION.md](PART_CREATION.md).

**Кандидат dev28: ошибки импорта (10.10.2026).** Исправлен внутренний legacy backend: общая область загрузки и валидации, канонические COM-идентичности при очистке, владение служебным флагом, проверка восстановления 3D Interconnect, первичная ошибка и diagnostics, запрет следующего импорта после неопределённого исхода. **2075 pure passed, 323 CAD deselected**; 29 новых pure-сценариев. Native-тесты добавлены, но не запускались: пустая сессия подтверждена после закрытия контрольных моделей; служебный флаг ещё не согласован. Публичный каталог остаётся 18 инструментов, импорта v2 пока нет. Пункт 1.4 и стадия 1 открыты. См. [Docs/IMPORT_CLEANUP.md](../Docs/IMPORT_CLEANUP.md).

**Проверен чистый wheel контура выпуска.** Wheel dev27 собран из `34bc3ff26f4d715cff802e6846cd64209beb7063` и установлен в отдельное locked-окружение. Проверены artifact/installed metadata/stdio, 18 схем, SHA/digest, без CAD/job-вызовов; это не native-приёмка. Рабочие v1 и исходная dev-установка не заменены, push/CI не выполнялись. Подробности в [Docs/FORK_RELEASE.md](../Docs/FORK_RELEASE.md).

**Локальный контур выпуска форка (10.10.2026).** Подготовлены tracked `uv.lock`, offline wheel validator и metadata-only stdio-проверка установленного wheel в отдельном окружении. CI сохраняет обязательное имя `unit-and-build`, добавляет проверку lock/build/installed metadata; артефакты сохраняются только при явном ручном запуске. Публикации в PyPI/MCP Registry/GitHub Releases нет; не опубликованный registry descriptor перенесён в справочный шаблон с незаполненным собственным PyPI-именем. Namespace и атрибуция upstream различаются явно.

Локально на историческом принятом dev27 wheel из `8cf1e42`: отдельная locked-установка Python 3.12.14, настоящий stdio, 18 инструментов/outputSchema, корректные SHA/digest; CAD/job-команды не вызывались. **2046 pure passed, 321 CAD deselected** в отдельном locked-окружении, 50 целевых artifact/metadata/packaging passed; actionlint и PowerShell Parser приняли workflow. Это не новая native-приёмка, не новый wheel из текущего HEAD и не GitHub CI run. Пункт 1.1 и все критерии стадий остаются открыты до полной проверки/выпуска; Контрольные документы после ошибочного legacy-прогона закрыты по прямому запросу пользователя; файлы не изменились, открытых документов нет. Служебный флаг CommandInProgress сохранён; его сброс и новый native baseline ещё не согласованы. Рабочая v1, все ограничения API и отложенный STL сохраняются. Push, CI и дополнительные агенты не запускались. См. [Docs/FORK_RELEASE.md](../Docs/FORK_RELEASE.md).

**Незавершённая локальная доработка: native opt-in и диагностика копии (10.10.2026).** Legacy CAD-тестам теперь нужен явный `--run-solidworks`; без него fixture не создаёт COM-сессию. При явном запуске также нужны пустая CAD-сессия и свободный `CommandInProgress`. Воспроизведение ошибочного фильтра `not native` пропустило 40 тестов сборок, не засчитывая их как пройденные. Правильный pure-фильтр — `not solidworks`. **1999 pure passed, 321 CAD deselected** в итоговом локальном прогоне; 33 целевых pure-теста покрывают opt-in, ограниченный oracle и классификацию недоступной ссылки. Порядок проверок описан в [Docs/NATIVE_TESTING.md](../Docs/NATIVE_TESTING.md).

Исследовательский пробник установленного dev27 дал отдельные native-наблюдения копирования и удаления в собственной копии: исходник и файл сохранились, persistent target восстановился, удалились ровно контрольное выдавливание и поглощённый эскиз, тело копии исчезло. Native вернул `Invalid=1` вместо `Deleted=4`; коды теперь разделены. Включение отключённого уравнения не имело наблюдаемого эффекта, определения остаются blocker. **Полная native-приёмка пробника не пройдена:** ошибочный локальный pytest-фильтр запустил legacy CAD-тесты одновременно с пробником; этот запуск остановлен, исходное состояние документов/служебного guard требует согласования. Новые native-записи удержаны. Публичный API и установленный wheel остаются dev27/18 инструментов; возможности копирования/удаления не объявляются. Все открытые пункты стадий 1–3, отложенный STL и сохранение рабочей v1 остаются в силе; агентов, push и CI не запускали.

**Текущее подтверждённое состояние: dev27 (10.10.2026).** Чистый установленный wheel из `8cf1e42226bc17e5975c5570cadf3dd1046f2422`, SHA-256 `ec7eae97e4c809d2f52022dcc34380161b6588a13a279815691710204a9394d9`. Общий STA frame устранил вложенный полный обход графа в контексте: два полных tree snapshots и два чтения relations/inventories закрываются одной проверкой canonical identity, конфигурации, полной tree revision и event sequence. Ошибочный outer context не коммитит dependency census cache. Native-регрессия сохранила граф из 25 узлов, четыре structural options, доступную строку уравнения/disabled counter и устойчивую привязку внешней ссылки на derived part из 36 узлов. Все 10 измеренных чтений graph/structure/context подтвердили по 2 полных перечисления дерева.

Контролируемое сравнение одного и того же сценария derived part (36 узлов, одна внешняя ссылка), два чтения на каждую сборку:

| Метрика одного чтения контекста | dev26 | dev27 |
| --- | --- | --- |
| Полные перечисления дерева | 4 | 2 |
| Чтения метаданных элементов | 156 | 84 |
| Явные Python → COM dispatches | 2308–2368 | 1561–1621 |
| Время, с | 16,80–17,47 | 10,77–11,38 |

Это измерения контрольных part-моделей; внутренних native RPC/C-slot comparisons и производительности сборок >1000 компонентов они не доказывают. Данные/ревизии при повторном чтении совпали; исходные документы, файлы, UI и собранные non-STL-настройки сохранены, собственные детали закрыты, пустая CAD-сессия подтверждена. **1966 pure passed, 321 native deselected**; публичный MCP stdio подтвердил 18 инструментов/outputSchema и корректный build metadata. Публичные размеры/переименование на dev27 ещё не прогонялись. Полное воздействие/удаление не реализовано и не разрешено; открыты отключённые определения и связи уравнений, другие конфигурации, непустые вспомогательные ссылки, аннотации/чертежи, входящие зависимости, native эффект/восстановление удаления, перенос базовых операций и остальные пункты стадий 1–3. STL остаётся отложенным; рабочая v1 сохранена. Новые агенты, push и CI не запускались. Ниже — история кандидатов.

**Кандидат dev27: общий frame графа и контекста.** Контекст больше не вызывает самостоятельный `dependencies` внутри своих границ: граф, native equation/reference inventories и per-feature привязки объединены одним одноразовым STA frame. Остаются два полных обхода дерева и два полных чтения relations/inventories; canonical identity, конфигурация, неизменяемая ревизия полного tree snapshot и завершающий event poll проверяются до возврата. Ошибка outer context не коммитит внутренний dependency census cache. Повторное выполнение фаз frame запрещено. Модель не изменяется, graph/context scopes сохраняются; полного воздействия/удаления по-прежнему нет.

На установленном чистом dev26 отдельно измерен baseline на собственном derived part: два последовательных чтения контекста подтвердили по **4 полных перечисления дерева**, с подсчётом явных Python → COM dispatches и QueryInterface. Это проверка исходного поведения, не приёмка новой оптимизации. **1966 pure passed, 321 native deselected**; Native-проверка dev27 должна подтвердить по 2 полных перечисления дерева, сохранение данных/ревизий и исходного состояния. Измерение явных dispatches не объявляется подсчётом внутренних native RPC и C-slot canonical comparisons. Старые native-приёмки не переносятся на новую сборку; каталог остаётся из 18 публичных инструментов. Все незавершённые пункты стадий 1–3 и решение отложить STL сохраняются.

**Текущее подтверждённое состояние: dev26 (10.10.2026).** Чистый установленный wheel из `b7cd2a81caf3f9e06bd136fa4a257cc1ff8f1e0f`, SHA-256 `39b291336c3859583c612330ae99af5c351a6bf48acf06764bf283458f6d71f6`. Привязка исходящих внешних ссылок реализована в `part_feature_deletion_context_v3`: прямые per-feature inventories связаны с закрытым native census и устойчивыми `object_id`, с учётом multiplicity/ambiguity и общего бюджета текста. В native-проверке собственной производной детали 36 узлов и одна внешняя ссылка дали единственное соответствие native ID 46 и восстановленный persistent target; все остальные узлы явно прочитаны с count=0. Два контекста совпали, исходный source-файл не менялся при чтениях. Это приёмка указанного part scope на контрольной модели; произвольные типы ссылок, другие конфигурации и входящие документы этим сценарием не проверены.

Отдельная same-wheel native-проверка приняла граф из 25 узлов, четыре structural options и контекст с доступной строкой уравнения и disabled counter. Отсутствующие определения отключённых уравнений остаются blocker. Обе проверки восстановили исходные документы/UI и non-STL-настройки, закрыли свои контрольные детали; после подтверждена пустая CAD-сессия. **1949 pure passed, 321 native deselected.** Настоящий MCP stdio подтвердил 18 инструментов/outputSchema и корректный build metadata dev26; публичные CAD-операции размеров/переименования на dev26 ещё не прогонялись. `deletion_impact_complete=false`, `deletion_authorized=false`, `stl_preferences_verified=false`; удаления и полного preview нет. Открыты уравнения/конфигурации, непустые вспомогательные ссылки, аннотации/чертежи, входящие зависимости, эффект/восстановление удаления и остальные пункты первой стадии. Следующая работа — объединение чтений графа/контекста в два полных снимка по границам, без повторных полных обходов внутри одного чтения; требуемые проверки контекста и canonical identity сохраняются. Весь план стадий 1–3 остаётся в силе, STL отложен. Новые агенты, push и CI не запускались. Ниже сохранена история кандидатов.

**Кандидат dev26: привязка исходящих внешних ссылок к элементам.** `feature.deletion_context` получает scope `part_feature_deletion_context_v3`; дополнительно дважды читаются прямые `IFeature.ListExternalFileReferencesCount/ListExternalFileReferences2` для каждого узла закрытого native census. Последние два OUT-значения feature API — скаляры, в отличие от document API. Native IDs служат только проверяемыми hints census; выбор writable объекта остаётся по `object_id` и persistent reference. Имена и индексы не являются writable anchors.

Сопоставление document/feature inventories сохраняет кратность одинаковых записей. Отсутствующие/лишние строки, неоднозначные соответствия и недоступный persistent target показываются отдельными blockers; вариант не выбирается произвольно. Ревизия включает оба полных снимка, граф и результат привязок; изменения между границами, canonical identity/конфигурации или событиями отклоняются. До 5000 узлов/суммарных feature reference rows, 16384 символа в поле и 2 Mi символов совместного equation/reference текста. Внешние документы не открываются, уравнения не решаются, записи модели не выполняются. **1949 pure passed, 321 native deselected**; Общая native-приёмка новой привязки ещё впереди; принятая проверка dev25 не переносится на dev26. Каталог по-прежнему 18 публичных инструментов, полное воздействие/удаление не опубликовано и не разрешено; остальные требования стадий 1–3 сохраняются.

**Текущее подтверждённое состояние (10.10.2026): dev25.** Исправлена native-семантика счётчиков уравнений; отключённые определения явно помечаются как недоступные и остаются в плане полного воздействия удаления. На чистом установленном wheel из `1425a5c` прошли две разные native-приёмки: граф/structural options/доступная строка уравнения/disabled counter и непустая внешняя ссылка собственной производной детали. Независимые document и feature API вернули одну и ту же запись с конфигурацией «Основная»; persistent target элемента восстановлен. Повторные полные context inventories совпали. Исходные документы и UI восстановлены, non-STL-настройки совпали, собственный source-файл при чтениях не изменился; обе проверки закрыли свои контрольные детали. Дополнительно подтверждена пустая CAD-сессия.

**1908 pure passed, 321 native deselected.** Настоящий MCP stdio установленного dev25 подтвердил 18 инструментов с outputSchema, `system_get_info`, версию, Git SHA и совпадение digest сборки. Это проверка каталога и диагностики; публичные CAD-операции размеров и переименования на dev25 ещё не прогонялись, их прежняя native-приёмка относится к dev21. Общая native-привязка внешних ссылок к устойчивым элементам, непустые вспомогательные ссылки, отключённые определения/связи уравнений, остальные конфигурации, аннотации, входящие ссылки, эффект и восстановление удаления остаются открыты. `deletion_impact_complete=false`, `deletion_authorized=false`; внутренний контекст не опубликован. Стадия 1 и все последующие стадии сохраняются в полном объёме. STL отложен, рабочая v1 и пользовательские правки сохранены, дополнительные агенты не запускались; коммиты локальные, push/CI не было. Ниже — история предыдущих кандидатов.

**Native-приёмка dev25 принята (10.10.2026):** чистый установленный wheel из `1425a5c95d734c2e11339524c2cecc9ed9fdfc38`, SHA-256 `70cf66dbe751567aaf37c8bc15314c733e02224e9bedc0657697b80d11e9790d`. На собственных моделях в SolidWorks 2023 подтверждены граф из 25 узлов, четыре сочетания structural options, доступная строка уравнения и отдельный счётчик отключённых уравнений; два context inventories и повторное чтение совпали. Пустые native-массивы обычных и вспомогательных ссылок проверены. Определение отключённого уравнения не прочитано; непустые внешние и вспомогательные ссылки пока не приняты. Исходные документы, геометрия, UI и non-STL-настройки сохранены; новые контрольные детали закрыты. `stl_preferences_verified=false`; полное воздействие и исполнение удаления не приняты. Публичный каталог остаётся из 18 инструментов; эти чтения внутренние. Подготовлена следующая отдельная проверка непустых внешних ссылок на собственной производной детали; её подготовка не является native-приёмкой. **1908 pure passed, 321 native deselected**; 25 новых pure-тестов проверили независимый oracle OUT-типов, конфигурационные скаляры feature API и отказ по чужому пути/элементу, неполному снимку или ложной authority. Push и CI не запускались. Стадия 1 открыта.

**Кандидат dev25 (10.10.2026), исправление после native dev24:** SolidWorks 2023 на двух созданных уравнениях после отключения одного вернул `GetCount=1`, `GetDisabledEquationCount=1`. Через ранее созданный отключённый индекс `Equation` вернул пустую строку; определение не считается прочитанным. Неверное предположение dev24 о включении отключённых строк в GetCount удалено. Scope изменён на `part_feature_deletion_context_v2`: `enumerated_count` и `disabled_count` разделены; `disabled_definitions_captured=false` и blocker `disabled_equation_definitions_unavailable` явно сохраняют непокрытую область. Определения отключённых уравнений остаются обязательной частью полного воздействия удаления, а не исключаются из плана.

Неуспешная native-проверка dev24 и её частные журналы сохранены без переписывания и повторения операций. После отдельного запроса пользователя две удержанные контрольные детали закрыты без сохранения: проверены точные имена, canonical identity, неизменённые stamps, конфигурации и ранее прочитанные уравнения; отсутствие документов подтверждено. Новая проверка dev25 будет использовать отдельные модели и журнал. **1883 pure passed, 321 native deselected**; полный локальный набор завершён успешно. Native dev25 ещё не принят, чтение непустых внешних/вспомогательных ссылок и полный preview не подтверждены. Каталог остаётся из 18 публичных инструментов; `feature.deletion_context` внутренний, `deletion_impact_complete=false`, `deletion_authorized=false`. Ниже сохранена история предыдущих кандидатов; более ранние статусы не описывают текущее состояние.

**Исходный кандидат dev24:** добавлено внутреннее чтение `feature.deletion_context(document_id, configuration)` со scope `part_feature_deletion_context_v1`. Два полных снимка native equation/reference inventories связаны с согласованным графом элементов и закрываются проверками canonical identity, конфигурации, документа и событий. Фиксируются строки/disabled/global-variable/configuration option уравнений, параметры связи с equation file, обычные внешние и вспомогательные ссылки. Повтор request_id читает прежний результат без нового обхода; запись этой операцией отклоняется до worker. Не вызываются EvaluateAll, обновление уравнений из файла, rebuild, активация или открытие зависимостей. Бюджеты: до 5000 строк каждой категории, 16384 символа в строке, суммарно 2 Mi символов. Имена и row_index не являются writable anchors.

Это очередной слой полного воздействия удаления из 1.4. Связи уравнение–размер–элемент, точный состав конфигураций уравнений, другие конфигурации дерева, аннотации/чертежи, входящие ссылки внешних документов, native привязка внешних ссылок к элементам и эффект/восстановление удаления остаются blockers. `deletion_impact_complete=false`, `deletion_authorized=false`; операция не опубликована. **1883 pure passed, 321 native deselected**; связанные 55 тестов проверили схему, изменение контекста, неизменяемый первый снимок, late notifications, idempotency, отсутствие native import в pure domain и остановку собственного equation setup без повторения после ошибки. Native-проверка нового wheel ещё впереди; установленный dev23 и его прежняя приёмка не подменяют dev24.

API-сигнатуры сверены с зарегистрированным SW31 и официальным описанием [IEquationMgr](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr_members.html), [Disabled](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IEquationMgr~Disabled.html) и [вспомогательных ссылок](https://help.solidworks.com/2023/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDoc2~ListAuxiliaryExternalFileReferences.html). Проверка зарегистрированных сигнатур не является native-приёмкой.

**Текущий итог (10.10.2026):** установлен чистый dev23 из `3a62dd3bb113f365ccb41e8176e2fb3f7f67b287`. Его внутренние `feature.dependencies` и `feature.deletion_structure` прошли native-проверку: 25 узлов, 6 parent links, 6 child links, 7 absorbed links, без parent/child расхождений. Независимые GetParents/GetChildren/GetOwnerFeature и восстановление persistent target совпали; повторное чтение сохранило граф и ревизию. Четыре сочетания children/absorbed вернули 1/1/2/2 структурных кандидата; каждое чтение заняло около 8 секунд. Исходные документы, геометрия, UI и non-STL-настройки сохранены, новые собственные детали закрыты. Уравнения, другие конфигурации, аннотации, внешние ссылки, точный результат удаления и восстановление после удаления ещё не охвачены; полного preview/удаления и публичной регистрации этих операций пока нет.

На предыдущем установленном dev21 приняты публичные размеры и переименование в каталоге из 18 инструментов: реальный MCP stdio, устойчивые ссылки, отсутствие повторной записи, stale/foreign/configuration отказы, история после перезапуска и восстановление исходной сессии. Эти свидетельства относятся к dev21 и не подменяют собственную публичную регрессию dev23. **1842 pure passed, 321 native deselected**. STL отложен по решению пользователя. По отдельному запросу закрыты без сохранения шесть старых тестовых деталей: точные имена, native-метаданные и элементы тестовых моделей проверены до закрытия, отсутствие документов подтверждено после. Последующая native-проверка dev23 восстановила исходную пустую сессию. Рабочая установка v1 сохранена; push и CI не запускались. Стадия 1 открыта.

**Актуальное решение пользователя (10.10.2026): STL отложен.** Доработка экспорта STL и выяснение изменения `stl_deviation` перенесены в стадию 3, пункт 3.2. Они не блокируют размеры, переименование и остальные работы стадии 1. В свежих проверках этих операций строго сравниваются все собранные настройки вне восьми известных STL-полей; полные исходные снимки сохраняются, но восстановление/приёмка настроек STL не заявляется. Прежние неуспешные проверки и журналы неизменны. Пользователь дополнительно подтвердил закрытие деталей второй попытки и сохранение текущей точности STL. Подтверждение сохранено отдельно; текущая проверка не перезапускается. Все документы, открытые на её старте, входят в неизменяемый исходный набор; используются отдельные собственные детали и журнал. Публичные размеры/переименование приняты на dev21; внутренний граф и структурный расчёт приняты на dev23. Далее — расширение полного воздействия удаления и собственная публичная регрессия dev23; импорт и базовые операции остаются в плане. Стадия 1 остаётся открытой.

**Новая публичная native-приёмка размеров принята на установленном dev21 (`f3f3001`).** Через настоящий MCP stdio подтверждены 18 инструментов, размер 7 → 9 мм, независимая геометрия 5 × 6 × 9 мм и объём 270 мм³, persistent reference после rebuild, отказ по неверному документу/конфигурации/единицам и stale revision. Повтор request_id и история после перезапуска не создают второй записи: в журнале ровно одна committed mutation. Исходные документы, файлы и UI восстановлены, новые собственные детали закрыты; non-STL-настройки совпали точно. `stl_preferences_verified=false`, восстановление STL-настроек не заявляется. Это приёмка поддерживаемого scope размеров, а не signed/sketch dimensions, произвольного BREP или ошибки native COM. Прежние неуспешные попытки сохранены.

Подготовлена отдельная native-проверка `scripts/verify_feature_dependencies.py`: чистый установленный wheel, две свежие собственные детали, два одинаковых закрытых графа, независимые GetParents/GetChildren/GetOwnerFeature, persistent target и четыре комбинации children/absorbed. Геометрия, исходные документы, UI и собранные non-STL-настройки проверяются отдельно; native-удаление не выполняется. При ошибке проверки собственные модели сохраняются. **67 связанных pure-тестов прошли**, общий набор **1842 passed, 321 native deselected**. Этот статус отражает подготовку сценария; native-приёмка графа ещё не выполнена.

**Текущий исходный кандидат dev23 (10.10.2026):** подготовлен внутренний read-only граф зависимостей элементов с отдельной ревизией `part_feature_dependency_graph_v1`. Он связывает полные снимки parent/child/absorbed relations с устойчивыми ссылками элементов, сохраняет явные расхождения parent/child и отклоняет изменение контекста, identity или уведомлений во время чтения. Повторное использование native ID проверяется через canonical identity; индекс узла не является ссылкой для записи. Служебные узлы без persistent reference остаются без `object_id`. Это основа пункта 1.4; полный просмотр последствий удаления и само удаление ещё не реализованы. Новый публичный инструмент не добавлен: каталог содержит 18 инструментов.

Последняя локальная проверка исходников и диагностических сценариев: **1814 pure passed, 321 native deselected**. Граф не проверен в native SolidWorks и не установлен. В dev-окружении остаётся чистый wheel dev21 (`f3f3001`), на котором ранее приняты внутренние размеры и внутренний/публичный экспорт. После согласования нового исходного состояния выполнена свежая публичная проверка размеров dev21. Запись 7 → 9 мм имеет succeeded/committed, но приёмка не пройдена: единственное поле расхождения — `stl_deviation`, 0,10488088481701517 → 0,11916375287812985 мм; quality=3 (Custom) и остальные 18 проверяемых настроек неизменны. Точные снимки сохранены в частном failure report. Две новые контрольные детали сохранены, дальнейшие CAD-вызовы остановлены до согласования нового исходного состояния. Причина изменения ещё не доказана; строгая проверка не ослаблена. Прежний журнал и committed запись не изменяются и не повторяются. Стадия 1 открыта; все оставшиеся пункты стадий 1–3 сохраняются. Дополнительные агенты, push и CI не запускались.

Подготовлен отдельный контрольный сценарий `scripts/diagnose_dimension_preferences.py`: прямые `SetSystemValue3` и `ForceRebuild3` только на собственной несохранённой детали, в явной конфигурации, с UI guard и заранее запланированной последовательностью 7 → 9 → 7 мм. Снимок настроек читается непосредственно после setter/rebuild; дополнительные чтения размера, контекста и физической геометрии имеют отдельные точки наблюдения. Намерение вызова записывается в эксклюзивный частный append-only trace с flush/fsync до native dispatch. При ошибке нет повторного вызова, возвратной записи или дальнейшего чтения модели, кроме обязательного освобождения собственного UI guard; сохраняются контрольные детали. Только точный возврат полной аналитической геометрии и всех настроек допускает закрытие контрольных деталей. Этот сценарий не запускает MCP и не объявляет приёмку; native-запуск ещё не выполнен и ожидает согласования оставшихся деталей. Связанные 19 pure-тестов и общий набор **1778 pure passed, 321 native deselected** прошли. Строгий публичный верификатор не ослаблен.

В dev23 добавлена внутренняя read-only операция `feature.deletion_structure`: по двум закрытым снимкам графа вычисляется консервативный структурный набор для выбранных persistent `object_ids` и явных флагов children/absorbed. Отдельная ревизия привязана к ревизии графа, выбранным узлам и флагам. Возвращаются причины включения, оставшиеся зависимые/поглощённые связи, потенциально затронутые оставшиеся узлы, циклы зависимостей, расхождения parent/child и узлы без persistent reference. Обход ограничен 5000 узлами и native-бюджетом связей, без рекурсии. Цикл владения эскизом вместе с обратной зависимостью операции допустим; циклическое владение отклоняется. Значения native delete flags 1/2 сверены с зарегистрированным swconst31. Вызов удаления не выполняется. Полное воздействие, уравнения, другие конфигурации, аннотации/чертежи, внешние ссылки и native-откат ещё не подтверждены и явно блокируют исполнение. `deletion_authorized=false`, `deletion_impact_complete=false`, `native_deletion_result_predicted=false`. Внутренний runtime сохраняет результат чтения без mutation checkpoint и повторяет request_id без нового обхода; путь записи отклоняется до worker. Связанные **53 pure-теста прошли**, native-приёмка ещё впереди. Публичный каталог по-прежнему содержит 18 инструментов, установленный wheel остаётся dev21.

Чистый wheel dev23 собран локально из `3a62dd3bb113f365ccb41e8176e2fb3f7f67b287`, без сети и установки. SHA-256 архива `c03030024af947821914597a2c071ee39329b8d2046d10323f9aa7b97871f253`; полный source digest файлов Python/guide в ZIP совпал с build manifest. Оба новых внутренних модуля включены. Установленный dev21 независимо проверен по версии, Git SHA и source digest и не изменён; native-приёмка dev23 не выполнена. Push/CI не запускались.

В завершении прямой диагностики устранено маскирование первичной ошибки: CoUninitialize и закрытие trace выполняются независимо, ошибки освобождения добавляются к исходной ошибке, а без успешно завершённого CoInitialize не вызывается CoUninitialize. Настоящий CLI проверен с fake pythoncom для ошибок инициализации, операции и summary I/O; **24 связанных pure-теста прошли**, общий набор — **1814 passed, 321 native deselected**. Native-операции и новые gates не выполнялись; установленный dev21, собранный wheel dev23 и прежние журналы не менялись. Следующий необходимый gate — запуск отдельного прямого контрольного сценария после подтверждения закрытия двух оставленных деталей. Полная стадия 1 и стадии 2–3 не завершены.

Предыдущие записи статуса ниже сохранены как история соответствующих сборок и попыток.

**Последний статус (10.10.2026):** стадия 1 открыта, в каталоге 18 реализованных инструментов. Чистый установленный dev21 (`f3f3001`, digest `72d3aaa9…`) прошёл внутреннюю пятиформатную проверку и публичный MCP stdio для STL мм/м/дюймы, STEP и Parasolid. Приняты координаты/масштаб STL, STEP SI units, поддерживаемая аналитическая геометрия источника, настройки/UI, идемпотентность и история после перезапуска. В обеих проверках исходная сессия восстановлена; один пустой staging оставлен с независимым подтверждением и явным манифестом. Внутренние размеры на том же wheel приняты: запись 7 → 9 мм и подтверждённый откат 11 → 9 мм после искусственной Python-ошибки. Публичная размерная проверка остановилась после committed записи: независимое сравнение общих настроек не прошло. Поля/значения расхождения не сохранены прежним верификатором, причина неизвестна; две контрольные детали и журнал оставлены, новые native-проверки ожидают согласования исходного состояния. Переименование в каталоге 18 инструментов ещё не перепроверено. Это не завершение стадии 1 и не приёмка произвольного BREP, signed/sketch dimensions, других форматов, roundtrip или native COM fault injection.

Исправлен верификатор публичных размеров: пассивное однократное чтение сохраняет exact scalar snapshots и changed fields до строгого отказа; типы и соседние float значения не приравниваются. Failure report записывается и при ошибке, ошибки записи отчёта не маскируют первичную ошибку; файл создаётся эксклюзивно. При held gate итоговый отчёт показывает требуемое сохранение моделей без дальнейших native baseline getter. **1745 pure passed, 321 native deselected**. Установленный wheel остаётся dev21 из `f3f3001`; Python-код пакета не изменён. Ни агенты, ни push/CI не запускались.

Проверка регистрации dev21: **1737 pure passed, 321 native deselected**. Каталог из 18 инструментов, outputSchema, русский guide и отказ экспорта без `--output-dir` проверены через настоящий MCP stdio. Следующие gates — чистый установленный wheel, внутренние операции на том же wheel и последовательная публичная native-приёмка. Стадия 1 не закрыта.

**Подготовка dev21 до native-проверок:** стадия 1 открыта. В исходном dev21 публичный каталог расширен до 18 реализованных инструментов: подключены три команды размеров и две экспорта. Обновлены system_get_info, guide и таблица миграции, в том числе ограничения аналитической геометрии и серверного каталога экспорта. Внутренние native-проверки размеров и пяти экспортов приняты на установленном dev19; новый чистый wheel и публичные команды требуют собственной последовательной приёмки. Регистрация не закрывает пункты 1.4 целиком: signed/sketch dimensions, произвольный BREP, остальные форматы, удаление/импорт и базовые операции остаются в полном плане. Агентов, push и CI не запускали.

**История принятого dev19:** стадия 1 открыта; публичный каталог содержит 13 инструментов. Пользователь закрыл контрольные детали dev18 и согласовал текущую точность STL как исходное состояние. Чистый установленный dev19 (`e32cfb3`) прошёл внутреннюю native-приёмку пяти экспортов: STL мм/м/дюймы, STEP и Parasolid. Проверены масштаб/координаты STL, unit declaration STEP, сохранность поддерживаемого аналитического BREP, настроек/UI, отсутствие повторного выполнения и результаты после переоткрытия журнала. Исходная сессия восстановлена, контрольные детали закрыты. Один пустой собственный staging оставлен при Windows error 32 с независимой проверкой identity/пустоты и явным отражением в манифесте. Геометрический roundtrip STEP/Parasolid, произвольный BREP и публичные MCP-команды не приняты. Старое задание dev18 `unknown/unresolved` и журнал не изменены. На том же установленном dev19 пройдена внутренняя проверка размеров: 7 → 9 мм с физической проверкой геометрии, повтор request_id без записи, stale revision отказ, после искусственной Python-ошибки за setter подтверждённый возврат 11 → 9 мм. Исходная сессия восстановлена. Публичные размерные команды, native COM fault injection и native-приёмка исходного dev20 ещё впереди.

В исходном dev20 подготовлен сборщик прямых зависимостей и поглощённых элементов для будущего предварительного просмотра удаления. Каждая ссылка проверяет canonical identity, чужие/коллидирующие ссылки и превышение бюджетов отклоняются; расхождения parent/child явно возвращаются. **1715 pure-тестов passed, 321 native deselected**. Полная оценка последствий, привязка к устойчивым ID/ревизии и native-приёмка ещё впереди; новый публичный инструмент не объявляется. Рабочая v1 сохранена, push/CI не выполнялись.

**История попытки dev18:** стадия 1 открыта; публичный каталог содержит 13 инструментов. Установленный dev18 подтвердил три STL-экспорта (мм/м/дюймы) и STEP: координаты/масштаб, сохранность поддерживаемой аналитической геометрии и настроек, checkpoint/UI guard и отсутствие повторного экспорта. На Parasolid после публикации файла удаление временного каталога завершилось Windows error 32. Задание имеет `unknown/unresolved`; выполнено 5 попыток SaveAs3, независимо подтверждены 4 операции. Две контрольные детали, пустой staging, файлы и журнал сохранены; следующие CAD-операции остановлены до согласования нового исходного состояния. Полная приёмка всех форматов и публичных MCP-команд ещё не выполнена.

Кандидат dev19 допускает явно оставленный пустой собственный staging только после подтверждённой публикации: строго Windows error 32, неизменная identity каталога, отсутствие reparse и любых записей, удалённый временный файл. Манифест содержит `staging_cleanup`; после native inspection повторно проверяются каталог, опубликованный файл, геометрия и настройки. Другие ошибки, подмена, непустой каталог, неподтверждённая публикация и ошибки native-проверки сохраняют unknown/hold. Оба верификатора независимо сверяют cleanup с durable evidence и реальной файловой системой. **1688 pure-тестов passed, 321 native deselected**. После согласования состояния новая внутренняя native-приёмка dev19 пройдена; прежнее unresolved задание не переигрывается и не объявляется успешным. Push/CI не выполнялись.

Read-only диагностика после отказа dev18: сохранённый Parasolid читается, заголовок распознан; staging пуст. Два getter рабочего каталога приложения дали одинаковое значение, не совпадающее со staging. Это не устанавливает владельца блокировки или причину Windows error 32; исходный рабочий каталог перед экспортом не был записан. Getter моделей, setter, восстановление, закрытие, удаление и replay не выполнялись.

Пользователь закрыл две контрольные детали после отказа dev15 и согласовал текущую точность STL как новое исходное состояние. Прежнее задание `unknown/unresolved` и его журнал сохранены без повторного исполнения или снятия hold. Установленный dev16 дважды завершился `failed/rolled_back` перед публикацией из-за буквального сравнения расширения файла; исходное состояние обеих попыток подтверждённо восстановлено.

Исходный кандидат dev18 исправляет STEP unit metadata: native-файл использует `SI_UNIT ( .MILLI., .METRE. )` с пробелом перед скобкой. Проверяется ссылка `GLOBAL_UNIT_ASSIGNED_CONTEXT` на `LENGTH_UNIT`, согласованность контекстов, отсутствие неоднозначных/неизвестных ссылок. Комментарии и строковые имена не используются как объявления единиц; русские строки не изменяют байты файла. Поддержаны SI мм/м; conversion-based length units явно отклоняются. Для полного ограниченного чтения STEP установлен предел 4 МиБ; расширение этого предела требует потокового разбора всех контекстов, а не проверки префикса. Разбор подтверждён на сохранённом собственном native STEP, но это read-only диагностика, не новая native-приёмка. **1659 pure-тестов passed, 321 native deselected**. Предстоят сборка и последовательные проверки чистого установленного dev18. Push/CI не выполнялись.

Кандидат dev16 сохраняет существующие native STL quality/deviation/angle и контролирует единицы, бинарный формат, систему координат и отсутствие сдвига в положительное пространство. Сохранённые настройки по-прежнему входят в точную ревизию, checkpoint и проверки; они не присваиваются инструменту как собственные изменения. Полная native-приёмка ещё не пройдена. Публичные размерные и экспортные инструменты ещё не зарегистрированы; их верификаторы подготовлены с supervisor и безопасной очисткой. Итоговый полный локальный прогон исходного dev16: **1629 passed, 321 native deselected**. CI не запускался, пакет не отправлен.

Повторная диагностика dev16 установила причину файлового отказа: `SaveAs3` создал единственный `model.STL` вместо запрошенного `model.stl`; файловая идентичность совпала, дополнительных файлов не было. Исходное состояние снова восстановлено. Кандидат dev17 проверяет единственную запись по идентичности проверенного файла и повторно проверяет идентичность временного каталога. Дополнительная запись запрещена даже при совпадении identity (hard link); подмена файла и reparse также отклоняются. **1634 pure-теста passed, 321 native deselected**. Предстоит проверка чистого установленного dev17; не считать это приёмкой экспорта или подключением новых публичных инструментов.

Read-only диагностика после отказа dev15: checkpoint STL deviation 0,915190966989661 мкм; запрошено 100 мкм; два последующих чтения дали 104,88088481701516 мкм точно. Это не доказывает внешнее редактирование: возможна нормализация или зависимость native-настроек, причина ещё не установлена. Диагностика не выполняла setter, активацию, чтение документов, закрытие моделей, повтор экспорта или снятие hold.

Для экономии лимитов ChatGPT далее работать одним агентом по умолчанию. Дополнительные агенты — только при существенной необходимости; не дублировать исследования и обзор одной задачи. Правило закреплено в `AGENTS.md`.

До следующей внутренней проверки добавлена отдельная защита очистки: gate закрывается перед dispatch и разрешает очистку только по совпавшей durable terminal записи, подтверждённому освобождению guard и отсутствию application holds. Неопределённость остаётся sticky; последующее задание не очищает прежнюю блокировку. При запрете тест сохраняет свои открытые модели, журнал и файлы; native cleanup и последующие native baseline readings не выполняются. **134 целевых pure-теста passed**, включая 59 новых регрессий; независимый обзор пройден. Это изменение верификатора, установленный wheel dev15 не менялся.

Дополнительно проверены export UI diagnostics и закрытие обоих ресурсов с сохранением исходной ошибки: **155 целевых pure-тестов passed**, независимый обзор пройден. Даже ответ `succeeded` не разрешает дальнейшие native-вызовы при неподтверждённой durable записи, освобождении guard или наличии application hold.

Оптимизация BREP прошла сравнение старого алгоритма и исходного кандидата на **одном собственном native-теле**: четыре полных снимка совпали точно, сравнения canonical identity сократились с 8348 до 3596, количество получений identity (339) и typed wrap (365) не изменилось. Время чтения 10,08–10,48 с не подтверждает заметного ускорения. Это read-only диагностика одного прямоугольного многогранника; проверка нового установленного wheel и других типов тел остаётся впереди.

Согласованный план. Стадии выполняются последовательно: **исправление → основной функционал → дополнительный функционал**. Переход к следующей стадии — после проверки результата текущей. Статус задачи меняется на завершённый только при наличии проверки; отсутствие лицензии, шаблона или тестовой модели не считается успешной проверкой.

## Дополнение: установленный dev28/dev29 и кандидат dev30

Dev28: 2075 pure/323 deselected; 18 tool metadata smoke accepted, native 2 passed/1 failed на ошибочной проверке void-setter. Независимо восстановленный baseline подтверждён; failed-отчёт сохранён. Dev29: 2076 pure/323 deselected; чистый wheel `63234a7`, digest `7d66a7829e32a592c0403adcfb6e7bc6f362f6b74d5c53dfcf6ce56ecbe61071`, SHA256 `7413119ab1a1d1b2bda6310d1d9cdca676d2384170a85050ae55ffa32e450499`, installed metadata/18 schemas accepted. Native 6 passed/1 failed; mass-error test не запускался. Четыре контрольных документа остались открытыми; non-STL baseline подтверждён, STL отложен. В dev30 исправлен DAG-порядок закрытия; 2081 pure/323 deselected, native pending. Публичного импорта v2 нет, стадия 1 не закрыта.

## Инженерный приоритет и измерения dev34 — 10.10.2026

По обновлённому PLAN.md общий импорт/экспорт отложен в 3.4 и исключён из gate стадии 1. Принятые восемь legacy native-сценариев dev32 сохраняются, их набор сейчас не расширяется. Приоритет: безопасная основа и ограниченные измерения → базовая деталь → листовой металл → чертежи → базовые сборки с библиотеками → сварные конструкции → конфигурации/большие сборки/PDM.

Dev33: выделение защищено Suspend/ResumeSelectionList; первый native-прогон 12 passed остановился на подготовке конфигурации, следующий 16 passed выявил обход document override после SelectedItems. Dev34 проверяет document override до выбора тел и повторно читает scoped options после Recalculate. IFeature теста заново получается после смены конфигурации; ACK подавления проверяется отдельно. Source pure — 2155 passed/323 CAD deselected; installed mass — 64 synthetic passed, artifact/metadata18 accepted без PYTHONPATH.

Первый mass native dev34: 22 сценария прошли, но неправильный cleanup callback сохранил модели — общая приёмка false. Callback исправлен; свежий полный прогон на wheel `c1a8a6025c4226d65d20e398a4312e1e530bff8a` дал 22 passed/accepted true с точным восстановлением выделения/камера/модель, всех 11 non-STL-настроек, пустым baseline и снятым guard. Все failed-отчёты сохранены. По постоянному разрешению пользователя собственные контрольные модели после завершения процессов закрывались без дополнительных вопросов. V1 сохранена, push/CI не запускались, публичный каталог остаётся18; стадия1 открыта. Следующий блок — безопасный перенос создания/редактирования детали в v2.

Итоговый полный pure-набор dev54: **2885 passed, 323 CAD deselected**, 29,39 с. Это проверка исходников, не native-приёмка.

Полный итоговый pure-набор исходного dev55: **2892 passed, 323 CAD deselected**, 28,77 с. Это не native-приёмка.

Dev55 первый internal native остановился после двух записанных случаев: создание пластины завершилось succeeded/committed с полным освобождением guard, но helper очистки не распознал новый scope. Прогон accepted=false и сохранён. После терминального процесса durable/job и фактическая геометрия сверены; только два собственных документа закрыты, baseline пуст/free. Исправлены оба verifier gates: точный новый scope/одна модель/все typed release-поля; busy допускается только как failed/not_started с native_mutation_started=false и untouched evidence, без разрешения сбрасывать чужой флаг. Связанные126 passed; после дополнения missing-error случая полный набор **2905 passed, 323 CAD deselected**,29,14 с. Код установленного wheel dev55 не менялся, новой сборки не требуется; свежая same-wheel native-приёмка впереди.

Второй dev55 internal native: семь записанных случаев прошли, в том числе thickness12→10 и русское rename. Busy корректно завершился failed/application_busy/not_started без заимствования, но record() ошибочно потребовал False как для собственного acquired guard. Прогон accepted=false; штатно fixtures_closed=true и command_flag_baseline_restored=true. Исправлена отдельная untouched-busy ветка record(); AST-pure тест выполняет саму функцию на реальных формах evidence и отрицательных вариантах. Связанные128 passed; итоговый полный набор **2906 passed, 323 CAD deselected**,28,78 с. CAD-код/wheel не менялся; свежий полный native-прогон необходим, предыдущие не объявлены принятыми.
