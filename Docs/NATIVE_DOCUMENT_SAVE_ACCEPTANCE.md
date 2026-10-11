# Приёмка сохранения существующего native-файла — dev82

Принято 11.10.2026 в scope `native_document_current_file_save_v1`.
Деталь, сборка и чертёж сохраняются ровно одним Save3 Silent по существующему
native-пути, с явными doc/config/revision/request_id. Первое сохранение,
публичные open/close и общий N0–N6 этим результатом не закрываются.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `1660a6857dc165d7c32beaa9ff418cdaa052ffbc` |
| Версия | `2.0.0.dev82` |
| Source digest | `b01774030b8fe317b982feef9aad3eb7f3b81734745c461efd3eb266a6adeb84` |
| Wheel SHA256 | `5d3d56ab466b0f44fe29e8b0e80b949e3157591597329eb7fd021435b0a58ca0` |
| Metadata report SHA256 | `f65b0461318c318bbd9245a75c02c4c91b8a300f18371b870637493e230dbec6` |
| Internal report SHA256 | `a9b42320a9e47221a2c0b4001dc86d3bf5135cb06cb47ff65e5a5a317c03aaa6` |
| Public report SHA256 | `8d086fdd3baf42c4e27ca1de52bbd92636ca9f226836858cae7f4b0a679bc363` |
| Verifier SHA256 | `daddc53a8f0485cf1268f52be157e7713b460ca210cc226e7215bb873f8130ba` |
| Geometry fixture SHA256 | `a87bdfc80e1fe2a94b54d26bef56cd92dfd63dffcfd9120d879946f86fb0d4a0` |
| Lifecycle helper SHA256 | `da5343db86b5dcae61a685ff4aa301b82f9121121e61588673cabebc174f779d` |

Internal10/public5 accepted=true, installed metadata67/19. Internal wall time
48.26 с, public 39.64 с; setup/readback/
cleanup включены, отдельное время COM не измерено. Журналы terminal:
internal {'failed': 3, 'succeeded': 7}, public {'failed': 1, 'succeeded': 12}; новых unknown/holds в принятых прогонах нет.

Реальная размерная правка детали сохранена и перечитана из отдельной native
копии:7 мм. Свойство сборки и новое имя листа чертежа также прочитаны с диска.
Перед сохранением сборки у её компонента оставлено собственное изменённое
свойство с явным dirty flag: SaveReferenced не включён, file SHA и dirty flag
компонента сохранены. Native копия сборки после открытия может быть dirty
из-за общего загруженного компонента; её без сохранения закрывает только стенд.
Этот readback не является реализацией/приёмкой публичных v2 open/close.

Public подтверждает три типа сохранения, request replay без второго Save3 и
stale refusal до native. Internal дополнительно проверяет три disk/native
oracles, inactive configuration и foreign document. Exact4-owned cleanup,
пустой/free baseline и non-STL preferences подтверждены отдельно после обоих
прогонов. Приёмка STL не заявляется. Pure4455 перед сборкой и итоговый4524
после69 новых проверок относятся к искусственным доменным/протокольным
сценариям;323 deselected не считаются CAD-успехом.

В public lifecycle guard-validator сохранено старое single-model правило для
других операций. Только exact native-save operation/scope допускает1–5000
guards по полному unique document_id census checkpoint; mismatch/duplicate/
missing census и unreleased guard отвергаются. Добавлены69 pure-регрессий
preflight/installed/public gates и supervisor; они не заменяют CAD-приёмку.

Ранее dev80 остановился до Save3 на распознавании root/sheet sketch. Dev81
получил unknown при обновлении заголовка чертежа; old job остаётся unknown,
после независимого наблюдения current state согласован, own fixtures закрыты,
повтор Save3 не выполнялся. У dev82 сохранены отказы подготовки dirty flag,
readback dirty assembly и старого public guard-validator. Они не переобъявлены
принятыми; final отчёты привязаны к своему verifier/lifecycle hash.

CAD, шаблоны, полный journal/report и реальные пути остаются в ignored work/.
Legacy-пилот20/20 на собственных source receipts dev78 не повторялся:
legacy-код не менялся; его результат не переносится на wheel v2 dev82.
Следующий обязательный остаток: [native lifecycle L1–L3](NATIVE_DOCUMENT_LIFECYCLE_DESIGN.md).
