# Подготовка кандидата dev97 — 14.10.2026

Статус: full source, wheel и installed metadata приняты в своих областях;
native-приёмка остаётся открытой. Стадия1 открыта. Dev97 установлен только в
dev-окружение; wheel и доказательства dev96 сохранены отдельно, рабочая v1
не менялась. Номер версии не переносит результаты между wheel.

Первый full source7a43c4b остановлен до завершения: project/lock были dev97,
package __version__ ещё dev96. Прогон не засчитан; изменяется только версия
пакета, затем выполняется новый full согласованного source-кандидата.

Full00b8f0d завершился normal exit1:11312 passed/1 failed/323 CAD deselected,
477,79 с. Единственный отказ — packaging registry template оставался dev96.
Кодовые проверки прошли, но full checkpoint не принят. Исправляется версия
непубликуемого template; packaging subset выполняется до нового full.

После исправления registry template packaging5 passed/0,10 с. Итоговый
full source49b899c завершился normal exit0: **11313 passed,323 CAD deselected
/479,47 с**. Source/tests во время итогового прогона не менялись.
Lock check --offline passed. Предыдущие failed/stopped прогоны не засчитаны.

| Установленный кандидат | Значение |
| --- | --- |
| Версия | 2.0.0.dev97 |
| Build Git | 49b899c9c6048c89be81e20c9c5c29f0e4ee50d4 |
| Source digest | ad83dc638a5df73c6511bf2d3d18600f82e2c299a235b86d8009ad3b0c513b36 |
| Wheel SHA256 | 702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b |
| Installed console/metadata | Accepted,83 tools; без source PYTHONPATH, cad_tools_called=[] |
| Короткий native owner/prefix probe | Normal exit0,247,71 с,59 returned steps;15 current anchors/четыре фазы и retained anchors разрешились; own cleanup/baseline; не приёмка B2 |
| B2 positive prerequisite | Positive1 terminal/normal exit0,2/2,6023,32 с; actual SQL6/3committed, own cleanup/baseline и пассивный exact gate подтверждены |
| B2 faults/N5/public gates | Fresh faults1 запущен после positive/cleanup; итог pending. N5/public не приняты; dev96 receipts не подставляются |
| GitHub | Один пакетный push25df8a6; actual PR CI38510604543 in_progress, PR15 draft, main не изменён |

## Законченный блок исправления

Dimension compound anchor разрешает owner feature через существующий строгий
feature PID resolver. Единственный current member, точный PID, native IsSame=1
для specific RefPlane и canonical принадлежность размера обязательны.
Display PID/slot/dimension roundtrip и direct dimension strategy сохранены.
Это устраняет расхождение resolver-контрактов; причина child-plane-5 N5 пока
не доказана и его failed/unknown не переписывается.

Linked-equation fixture удерживает exact file identity/timestamps/bytes/SHA
до Add2 и проверяет их после полного setup. Native labels и owner binding
не меняются; никаких новых инженерных операций или публичных инструментов.

## Фактические проверки до полного кандидата

| Область | Результат | Граница |
| --- | --- | --- |
| Equation fixture/ancillary | 130 pure passed /5,80 с, normal exit0 | Artificial native calls; CAD не запускался; два ACL-denied запуска не засчитаны |
| Root equation wrapper/session/refusal | 91 pure passed /31,41 с, normal exit0 | Реальный journal и fake-native adapter; CAD не запускался |
| Dimension owner/annotation/domain/enum | 133 pure passed /3,29 с, normal exit0 | Real production feature resolver с fake-native pointers; первый artificial fixture mismatch127/6failed сохранён отдельно |
| Dev96 prefix/slot probe8 | Normal187,46 с,59 returned steps,15 anchors/четыре фазы, own cleanup/baseline | Exact installed dev96, mismatch не воспроизведён; не приёмка dev97 |
| Dev96 empty-plane resolver probe | Normal9,56 с, три current planes, own cleanup/baseline | Exact installed dev96; текущий raw-specific alias не воспроизведён |

## Следующие конечные действия

Конечные случаи, критерии и ограничения preview/delete сведены в
[очередь B2 dev97](B2_DEV97_REMAINING.md). Пока native positive выполняется,
подготовка идёт без COM; historical dev96 receipts не подставляются.

1. Зафиксировать source/version/lock и выполнить один full pure с CAD exclusion
   и fresh внешним basetemp. Во время проверки source/tests не менять.
2. После normal full собрать и установить dev97 только в dev-окружение;
   сохранить точные Git/source digest/wheel SHA. Проверить console/metadata
   без source PYTHONPATH. Рабочую v1 сохранить.
3. Выполнить короткую native-проверку изменённого owner resolver и полной
   последовательности чтений; при отказе проверить исходное состояние и
   собственную очистку, не повторять unknown операцию автоматически.
4. Пройти обязательные внутренние B2 prerequisite gates на exact новом wheel,
   затем finite child-plane/unused-equation/linked-equation и public B2.
   Dev96 positive/fault receipts в gate dev97 не подставлять.
5. Свести B2 и продолжить конечные B3/B4/B5 до сквозной приёмки стадии1.
   Перенесённые D2/D3 остаются в PLAN.md. Source/CI-only проверки не заменяют native.

Изменения накапливаются локально. Новый CI — после пакетной отправки,
PR15 остаётся draft. Частные CAD, шаблоны, файлы уравнений и журналы вне Git.
