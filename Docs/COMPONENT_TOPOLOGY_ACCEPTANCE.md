# Приёмка topology экземпляров

**Принято 11.10.2026**: dev74 для `resolved_assembly_instance_topology_reads_v1`.
4210 pure passed/323 CAD deselected (53,35с), installed metadata59 инструментов/
18 guarded операций; internal native21/public MCP8, оба `accepted=true` на
одном exact wheel. Три новых passive face/edge чтения. Диагностическая проверка
binding82 references учитывается отдельно и не заменяет эту приёмку.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `592b876d5839cef91ba6e0d629d1f86658e663e7` |
| Source digest | `a18859006874577f13c2fbe63cf1443afcc8f797468115be83e9ecb2c41c5ac9` |
| Wheel SHA256 | `ca2616976905950402286644742b24234e99a6a3a54a9192870a6efb04fd55ae` |
| Verifier SHA256 | `fd8d9e41831c6084750ba091a3a46171923fd46b250d541cba9f7e0356c3efe1` |
| Fixture helper SHA256 | `f68f54779ea0c83669174d272d3f630e4402a1a9e78b76495a454acd103d0306` |
| Internal report SHA256 | `70e929a1a24ac57dbcddffdd2f9233369660c487c824349a8402595cb031fe7d` |
| Public report SHA256 | `af986847337ae7da013a7294bfa154d76a429ebb354f9c9e050bca19660f04ef` |
| SolidWorks | `31.2.1` |

Приватные отчёты: `work/native-topology-dev74-1/report.json`,
`work/native-topology-mcp-dev74-1/report.json`, metadata
`work/metadata-dev74-1-report.json`. Оба прогона успешны с первой попытки;
все read-only jobs terminal, новых unknown нет. Каждый прогон создал и закрыл
только свои четыре документа; native empty/free baseline и non-STL preferences
восстановлены. Реальные CAD/отчёты/SQLite остаются в ignored work/.

Verifier `scripts/verify_component_topology.py`: internal21/public8 на одном
exact installed wheel без PYTHONPATH. Общие свои fixtures: repeated-file configs,
nested path, скрытые тело/экземпляр, два блока20×10×5, поверхность15×10,
цилиндрØ12×30. Analytic area/length/local endpoints, root transform отдельно;
roundtrip/membership, страницы, known native rename/config-change/delete/recreate
отказы, passive UI/model state и request replay. Полный pure/metadata и exact
terminal ownership cleanup обязательны. Public не дублирует internal-отказы.

S1-04/S1-05/S1-06 и общий gate стадии1 остаются открытыми; эта scoped приёмка
не подтверждает всю область native состояний/мутаций или измерения сборок.

Native доказаны точный instance/body owner и persistent-reference roundtrip
для planar solid/surface и cylinder faces/closed edges; разные referenced
configs и rotated/shifted/nested контекст, скрытые тело/экземпляр, локальные
координаты, pagination, native rename original face reference, changed-config
отказ, удалённый и пересозданный экземпляр того же файла без reassignment.
Public проверяет три новых инструмента, explicit ownership, foreign rejection,
request replay и durable journal. Удаление выполнял только fixture-builder;
публичная delete_feature/impact/restoration этим не реализована и не принята.

Открыто: suppressed/lightweight/SpeedPak/mesh/assembly-cut состояния, общая
native-область surface geometry/замены внутренней topology существующей детали,
frame/измерения сборок, mutation revisions/restore и единый итоговый N0–N6 wheel.
