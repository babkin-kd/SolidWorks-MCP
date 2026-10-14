# Приёмка U-развёртки dev68 — 11.10.2026

На одном точном установленном wheel приняты **internal native 9/9** и
**public MCP 10/10**, оба `accepted=true`. Это ограниченный scope
`single_u_sheet_flat_state_v1`, а не завершение стадии 1 или всего листового металла.

- Версия: `2.0.0.dev68`.
- Git: `ff5f03803fae5dd50efa0badfe77295dc15642b2`.
- Source digest: `9b6b83d336de326864ca6f138c14db8d41deac746a5197baea7881fb4310d321`.
- Wheel SHA256: `aa8f4cb2c31a844e017fb927710518c35ce36d43a44ebb196e2450fc77aeae3f`.
- Pure исходников:3997 passed /323 CAD deselected,50,43 с.
- Installed metadata:48 инструментов /17 мутаций; без CAD.
- Установлен только в dev `.venv`, без PYTHONPATH исходников; v1 сохранена.

## Что подтверждено

Собственное L-основание с t=2 мм, длиной30 мм, r1=2 мм/K1=0,42 и
отбортовкой15 мм, r2=2,5 мм/K2=0,38. Физическая U-форма и полная плоская
форма проверены аналитическим oracle, native mass/параметрами и полной
привязкой собственных элементов. Размеры, два K-фактора, профиль, тела,
persistent references и русские имена сохраняются. Направление сгиба и
возврат исходной геометрии проверены; другие углы/профили не приняты.

Внутренний прогон подтвердил stale до записи и оба известных отказа с
проверенным scoped restoration (`rolled_back`). Публичный stdio подтвердил
создание L/U, развёртку, обратное сгибание и request_id replay: повтор не
создаёт вторую операцию. Журнал и доказательства освобождения guard проверены
до очистки. Исходная отдельная контрольная модель сохранялась во время операций.

Оба процесса завершились. Все собственные контрольные документы закрыты;
исходный пустой/free baseline и служебный флаг подтверждены. Новых unknown нет.
STL-приёмка и экспорт не выполнялись; используются согласованные текущие
настройки, не-STL-настройки проверены общим стендом.

Приватные отчёты/журналы/CAD остаются в work, в Git не включены.

## Конечные сценарии

Internal:
- `new_part_from_empty_session` — passed.
- `new_part_preserves_existing_document` — passed.
- `native_u_state_l_source_created` — passed.
- `native_u_state_flange_source_created` — passed.
- `u_state_stale_prewrite_rejected` — passed.
- `u_unfold_known_failure_scoped_restoration` — passed.
- `native_u_sheet_flat_state` — passed.
- `u_refold_known_failure_scoped_restoration` — passed.
- `native_u_sheet_folded_state_restored` — passed.

Public MCP:
- `public_new_document_stale_prewrite_rejected` — passed.
- `public_new_part_from_empty_session` — passed.
- `same_request_does_not_create_second_document` — passed.
- `public_new_part_preserves_existing_document` — passed.
- `public_flange_source_created` — passed.
- `public_native_full_edge_flange_u` — passed.
- `same_request_does_not_repeat_flange` — passed.
- `public_native_u_sheet_flat_state` — passed.
- `same_request_does_not_repeat_u_flat_state` — passed.
- `public_native_u_sheet_folded_state` — passed.

Контракт — [SHEET_FLANGE_FLAT_STATE.md](SHEET_FLANGE_FLAT_STATE.md).
Остатки стадии 1 — [STAGE_1_REQUIREMENTS_MATRIX.md](STAGE_1_REQUIREMENTS_MATRIX.md).
