# B2: returned IRefPlane — 14.10.2026

Короткие native-пробы выполнялись последовательно на установленном
`2.0.0.dev96`, Git `f80ee6d80819140a8122fcf26104b0ce6760bff8`, wheel SHA256
`9088e018be898cf94e5c9bbbd1023ee09cb6c9f0a9af24a9ed66f48b3a9380fa`.
Package source и публичный каталог не менялись. Исходники CAD-пакета не
подключались через PYTHONPATH. Собственные модели/журналы остаются вне Git.

| Проба | Наблюдение | Очистка |
| --- | --- | --- |
| 1 | Ошибка probe: drawing template10 вместо part8, отказ до InsertRefPlane | Отдельная terminal own cleanup/baseline |
| 2, 2,98 с до отказа | Raw и QI(IFeature) canonicals совпали, canonical нового feature отличается. GetTypeName2 у returned QI завершился DISP_E_MEMBERNOTFOUND | После возврата getter освобождён только idle test-owner; отдельная own cleanup/baseline |
| 3, 3,33 с | Raw и current-specific canonicals различаются; transforms совпадают. Current feature PID roundtrip подтверждён | Normal exit0, own cleanup/baseline |
| 4, 3,28 с | Raw/current-specific/new feature имеют одинаковые непустые PID; native IsSame(raw,specific) вернул int1 | Normal exit0, own cleanup/baseline |
| 5, 3,36 с | Новый explicit native bridge подтвердил обе границы PID/IsSame/roundtrip и полный original/current census23→24 | Normal exit0, own cleanup/baseline |

Различие COM wrappers само по себе не доказывает различие native объектов.
Официальный [ISldWorks.IsSame](https://help.solidworks.com/2021/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~IsSame.html)
предоставляет native object equality; наблюдаемая совместимость подтверждена
пробой4, а применение verifier helper — пробой5. Геометрия/имя не используются
как доказательство адресации. В production уже существует отдельная проверка
IRefPlane PID с native IsSame в `cad_geometry.resolve_persistent_id`.

Подготовка N5 явно выбирает native bridge до QI(IFeature), а не делает fallback
после ошибки другого пути. Требуются полный original feature census с
неизменным порядком, ровно одна новая RefPlane, сохранение own canonicals при
QI(IRefPlane), одинаковые непустые native PID трёх объектов, строго int1 от
IsSame и roundtrip к точному current feature. Closing boundary повторяет
проверку. Значения0/2/bool, пустые/чужие PID, исключения и изменение состава
дерева отвергаются. Default strict canonical binder для остальных callers
сохранён. Привязка сама не выдаёт полномочий на удаление или cleanup.

Итоговый related source-набор: **194 pure passed /31,73 с**, normal exit0.
Artificial handles/native callbacks; реальные SQLite/JobRunner в fixture/driver
проверках. Отдельные6 final-census regressions passed /0,12 с; full final
candidate ещё требуется. После bridge callbacks повторно проверяется полный
original/current census, чтобы изменение внутри closing reads не выпадало
из приёмочного envelope. Этот последний final-census read добавлен после
probe5 и ещё не имеет собственной full N5-приёмки.

Installed preflight без CAD подтвердил wheel, исходный accepted positive report
SHA/actual SQL и11 неизменных positive helpers; следующий N5 фиксирует31
helper SHA. Preflight не заменяет native-приёмку.

Это диагностическая совместимость, **не N5/B2/public acceptance**. Probe
использует пустую собственную деталь и offset от стандартной плоскости;
зависимость от грани основания и полная refusal session ещё требуют конечного
N5. Старые failed/unknown jobs не меняются и не повторяются.

SHA256 частных доказательств:

- Probe2: `0d290775c3072b2e4521cf8ce90e075c55500acd2413d0e49e69f34b978ad4b5`.
- Cleanup2: `c8c6a75ec444c23d181191f929981c2dde4c5d5e35327a7f3e06b2e1a07f248f`.
- Probe3: `8e8fb7d817b9892a4b96f11246a1ecf359416e8ad5e708a454e901375af5f616`.
- Probe4: `90edf2e2a0304718661f8ed25dda34aa6db326caf236882aef996eac6e1c1eb3`.
- Probe5: `e41165d93abf4e5434946eb7ef4dfaaaf25556a90017beb10491c7a6302bc902`.

B2, B3–B5 и стадия1 остаются открытыми. Следующий шаг — новый N5 child-plane
с фиксированными helper SHA, затем unused/linked cases и публичная цепочка.
