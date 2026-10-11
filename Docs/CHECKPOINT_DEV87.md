# Локальная контрольная точка dev87: открытие и конечная граница стадии 1

Второй законченный lifecycle-блок после пакетной отправки dev82:
clean close dev85 и bounded native open dev87. Приёмка открытия:
internal13/13, 210,07 с; public MCP11/11, 189,68 с; оба accepted=true на одном
точном установленном wheel. Installed metadata71/21, output schemas подтверждены.
Source pure5560 passed/323 CAD deselected, 77,43 с; после правок только external
verifier related499 passed, 1,15 с. Пакет после wheel не менялся.

- Версия: `2.0.0.dev87`.
- Wheel Git: `6437b337b01300a73c3b97a7604c2fb5cad58729`.
- Source digest: `ec4e6a56d215a6d3e37b447cc4125635ebd05e495b3fdc16f940fcd50f97caa2`.
- Wheel SHA256: `97d19212f115e34b5fa1ba618f838406396f24e63a24838617c0a3d5aa52d971`.

Подтверждены part/config/read-only, saved resolved assembly/drawing,
new/borrowed references и actual referenced configuration geometry. Dirty
сосед/исходные файлы/окна/selection/view/CWD и прочие application settings
в поддержанной области сохранены. Scoped failure/rollback, replay/stale и
exact-owned cleanup проверены. В финальных журналах unknown нет; сессия пуст/free.
Прежние failures/unknown оставлены без изменения. COM throw остаётся pure-only;
Python fault после normal native return не выдаётся за реальную COM-ошибку.
Точные hashes, признаки и ограничения: [приёмка](NATIVE_DOCUMENT_OPEN_ACCEPTANCE.md).

## Пересмотр плана по запросу пользователя

Стадия 1 теперь имеет семь конечных блоков: L2 закрыт, L3/S1-B1…S1-B5 открыты.
Минимальный пользовательский результат — русская simple part → existing plane →
rectangular sketch → blind extrusion → length edit → first native save →
close/open → length edit/Save3 → close при dirty соседней модели.
Каждому остатку заданы результат, поддержанные случаи и конечная приёмка.

Явная адресация/ревизия/request_id, полный supported checkpoint, STA/journal/
holds/no-retry, postconditions и обязательный native gate не перенесены.
Все22 прежних требования прослеживаются;20 широких D2/D3 задач остаются
видимыми и незавершёнными. Исторические scopes не заменяют same-wheel S1-B5.
[План](../PLAN.md), [матрица](STAGE_1_REQUIREMENTS_MATRIX.md),
[критерии](STAGE_1_BLOCK_ACCEPTANCE.md).

## Пакетная отправка

Изменения остаются в локальных коммитах до 3–5 законченных блоков либо конца
рабочего дня. Нового push/CI нет. Последний remote CI run38146512142 — failure;
исправление fresh-checkout SQLite setup включено в успешный pure dev87.
Оно отправится общим пакетом со штатным CI; draft PR15 и stable main сохранены.
Native-приёмка L2 не закрывает remote CI или всю стадию 1.
Следующий блок — L3 own unsaved part1cfg/1solid/no refs, без расширения scope.
