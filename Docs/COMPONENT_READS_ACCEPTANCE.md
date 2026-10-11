# Приёмка чтения экземпляров сборки

**Принято 11.10.2026** в scope `resolved_assembly_instance_reads_v1`:
установленный dev73, полный pure-набор4175 passed/323 CAD deselected
(53,33с), installed metadata56 инструментов/18 guarded операций,
internal native15/public MCP6, оба `accepted=true` на одном wheel.

| Привязка | Значение |
| --- | --- |
| Git исходников wheel | `5a531efc0c96602323f70b2c84bb89d02ef2b5b2` |
| Source digest | `fc116c6784f792a9d85ef68ad7a0f0f8dab28a938cb147ea56e425cd6e3fd665` |
| Wheel SHA256 | `c99171339ed8b01f55261d71b2b5c62145859379b4ccb3cdf9fa6dc29748fef8` |
| Verifier SHA256 | `4fcc5c023053e9b826d86e7c01bc5fa74c36144cf092a4c53c5aa0d1c25d30e1` |
| Internal report SHA256 | `40d0d94e3af573110e90834d5d834d46351ad2eb4116056f4171a9004bdb6d14` |
| Public report SHA256 | `f12383e0f87d4222a7b3a5e3c7edbd405bf39947b177f0cacd5eb0a74e73ad31` |
| SolidWorks | `31.2.1` |

Приватные отчёты: `work/native-components-dev73-3/report.json` и
`work/native-components-mcp-dev73-1/report.json`; installed metadata —
`work/metadata-dev73-1-report.json`. Обе CAD-проверки завершены, exact-owned
четыре fixtures закрыты без дополнительного сохранения, исходная пуст/free
сессия и non-STL preferences восстановлены; все jobs terminal, новых unknown нет.

Verifier `scripts/verify_component_reads.py`: internal15/public6, только свои
fixtures — multibody solid/surface часть с двумя геометрически различными
конфигурациями, другая деталь, saved подсборка и root сборка с повторными
экземплярами. Аналитические local bounds/transform/parent paths, roundtrip
ссылок, сохранение native UI/configuration/document state. Public через stdio
проверяет четыре инструментальных чтения, чужое тело и request replay;
internal дополнительно проверяет native rename/configuration changes и отказы.

Все real CAD и private reports остаются в ignored work/. Приёмка требует
точного установленного wheel без PYTHONPATH, полного pure-набора, metadata,
terminal jobs, exact ownership cleanup и восстановления исходной сессии.
Skipped CAD не считаются passed. Ни строки S1-04/S1-05 целиком, ни стадия1
не закрываются только этим блоком; topology/прочие состояния остаются открытыми.

Два первых прогона не засчитаны: ошибка доступа к constants класса pywin32
(12 завершённых случаев), затем слишком узкое ожидание кода отказа при смене
referenced configuration (14). Native смена конфигурации может также заменить
COM-identity, поэтому безопасный persistent_reference_mismatch подтверждает
отказ старой ссылки наряду с component_reference_context_changed. Исправлялся
только verifier вне wheel; package/source digest не менялись. Неуспешные отчёты
сохранены; после terminal-proof выполнена собственная cleanup без переобъявления
их успехом. Последний internal и public — отдельные свежие полные прогоны.

Native приняты repeated-file instances/геометрически разные referenced configs,
parent paths, rotated/shifted transform, normal solid/surface body roundtrip,
rename original component reference, stale/foreign/inactive и changed-config
отказы. Mirrored transform, suppressed/lightweight/SpeedPak/assembly-cut,
удалённые/recreated native экземпляры, component face/edge refs, крупные сборки,
расстояния/масса/точные bounds сборки и общий финальный кандидат ещё не приняты.
