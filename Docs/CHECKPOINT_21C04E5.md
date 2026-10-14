# Source-контрольная точка 21c04e5 — 14.10.2026

Накопленный пакет завершил один full pure на точном source
`21c04e5b3fb78612e7f9312ed53f4b544ac9f2d4`: **11463 passed,323 CAD deselected
/483,88 с**, normal exit0. Source/tests не менялись во время прогона;
fresh внешний basetemp, cacheprovider off, фильтр not solidworks.
Исключённые CAD-тесты не являются пройденными.

| Завершённая область подготовки | Проверка | Граница |
| --- | --- | --- |
| Armable original finish seam | 58 related pure /1,97 с | Runtime/JobRunner/PythonWorker/SQLite с искусственными callbacks, без CAD/Q |
| Installed unarmed seam wiring | 109 related pure /1,75 с; actual attempts4/5 normal exit0, SDK83, journal=[] | Exact original store/proxy/runtime, unarmed/runner absent, normal close и factories restored; CAD/job calls=[] |
| Public B2 candidate binding | 121 related pure /55,61 с; actual dev96 reports отвергнуты для dev97 до provider | Exact requested version/build и все прежние wheel/SQL/helper gates; historical unknown не изменён, CAD не вызывался |
| Dimension transport admission | 37 related pure /0,47 с | Exact finite requests, atomic validate/write/flush, permanent close, unknown partial write; artificial pipes, native Q/stop/restart/cleanup false/not_run |
| Installed timing diagnostics | Enabled/disabled по20 metadata запросов,22/0 records; отдельный storage fault и обязательный journal schema3, jobs0/mutations0 | Exact installed dev97, normal SDK close, native_acceptance=false; реальные mutation/restore/hold timings не приняты |

Точный installed/native кандидат остаётся `2.0.0.dev97`, build
`49b899c9c6048c89be81e20c9c5c29f0e4ee50d4`, source digest
`ad83dc638a5df73c6511bf2d3d18600f82e2c299a235b86d8009ad3b0c513b36`,
wheel SHA `702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b`.
Production source/version/lock относительно этого build не менялись;
новые verifier scripts вне wheel. Рабочая установка v1 сохранена.

Native B2 positive продолжается: preparation succeeded, delete пока pending.
Cleanup/baseline и общий B2 не приняты до terminal отчёта. Конечная
[очередь dev97](B2_DEV97_REMAINING.md) сохраняет faults/N5/public gates;
dev96 receipts не переносятся. Native B3/B4/B5 и вся стадия1 остаются открыты.
Следующий B4 integration gate — one-shot actual target job ID binding,
installed transport и independently proved callback/guard/admission Q.

Прямые Git/API-проверки: origin/main остаётся `3ab795e`, PR15 open/draft,
remote head `eaf5e5b`, mergeable=true. Новый push/CI на момент этой сводки
не выполнен; необходимая native-приёмка продолжается и не прерывается ради Git.
Реальные модели, частные пути и полные отчёты/журналы остаются в ignored work/.
