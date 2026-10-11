# Приёмка чтения экземпляров сборки

Исходный кандидат dev73 подготовлен для `resolved_assembly_instance_reads_v1`.
Пока **не принят**. Нет засчитанной установленной/native проверки этой области.

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
