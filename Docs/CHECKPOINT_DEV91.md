# Локальная контрольная точка dev91: exact-owned annotation views B1

Исправление bounded rectangle stages установлено только в dev-окружение;
рабочая v1 сохранена. Открытие L2 не расширено. **B1 не принят:** положительный
сценарий, отказы/восстановление и public MCP требуют native-свидетельств этого wheel.

## Точный кандидат

- Версия: `2.0.0.dev91`.
- Git: `301edeabb5f298b52ef7471b65417fc6db3af22f`, clean build.
- Source digest: `4440a0d5adf967c0e2656883a9e879ccfdae42ee21a2ab04d875e904c5699017`.
- Wheel SHA256: `09ba36986ef44ba6a7605b61c9cd50ae4dcaa5536a4a8ac7626b9df0322beedd`.
- Full source pure: **6567 passed /323 CAD deselected, 138,38 с**.
- Offline wheel gate и installed metadata/stdio: **79 tools /25 mutations**,
  schema/provenance приняты, без source `PYTHONPATH`. CAD tools не вызывались.

Private evidence: `work/pytest-dev91-full-1.log`, `work/wheel-dev91-report-1.json`,
`work/metadata-dev91-report-1.json`. Полные journals/models остаются вне Git.

## Изменение и граница доказательств

Отдельные sketch/extrusion receipts сохраняют baseline views. Actual dimensions
нового элемента связывают один новый view; tree feature selection подтверждает
точную native identity. После доказанного geometry inverse удаляется только этот
пустой unused view. Полный restored разрешён лишь после возврата baseline views
и независимого whole-session gate. Journal labels уникальны, inverse one-shot;
lost/false ACK, чужая замена и неполный readback удерживают unknown без повторов.

Short interop dev90 подтвердил связку и удаление двух своих views со всеми
baseline/cleanup, но использовал прежний box-builder. Это не приёмка новых
sketch/extrusion tools; [факты и SHA256](CHECKPOINT_DEV90.md#exact-owned-view-retirement-interop-и-source-интеграция).
Historical dev90 unknown сохранён, его request не повторяется.

## Остаток

Конечные B1 N1…N5: independent sketch-only → blind extrusion 40×20×10/8000,
точная plane/neighbor, русские имена и stable result IDs, stale/replay/unsupported
отказы, полный scoped restoration либо ожидаемый unknown/hold fault-case.
Internal native и public MCP проверяются на этом exact wheel; installed metadata
и source pure не заменяют их. B2…B5 и перенесённые D2/D3 задачи остаются.
Изменения накапливаются локально; нового push/CI нет.

## Текущий native-прогон

Запущен `verify_rectangle_stages_positive.py` на exact installed dev91;
private `work/native-rectangle-dev91-positive-1/report.json`, один CAD-владелец.
Пока `positive_case_passed=false` и `accepted=false`, ни один native gate B1
не закрыт. Runtime/helper hashes фиксированы; работающий wheel и helpers
не изменяются. Остальные fault/public условия остаются после этого finite positive.

## Подготовленный следующий блок, не запущен

Для N5 внешний restoration gate учитывает точный ledger двух отдельных stages:
максимум32 rows sketch и34 extrusion после добавления обязательных view steps.
Related93 pure/6,04 с проверили actual JobStore/artificial baseline, native-shaped
step sequence и отказ overflow/duplicate/lost acknowledgement. Это не новая
native-приёмка восстановления. Этот verifier не используется live positive;
ни один helper его frozen manifest не изменён.

Добавлены passive `verifier_rectangle_positive_acceptance.py` и отдельный
`verify_rectangle_stages_faults.py`. Gate связывает exact wheel/helper hashes,
четыре positive labels, оба committed jobs, borrowed sketch ID, native readback
и original cleanup baseline; running/partial/foreign reports не допускаются.
Driver содержит четыре stale/foreign prewrite случая и два controlled observation
faults после нормально завершившегося native snapshot, с отдельным own restoration
эскиза/выдавливания и replay. Он не имитирует реальный COM throw. Его native
приёмка **не запускалась**. Pure preflight/ledger105 passed/6,08 с; driver/preflight/
restoration56 passed/4,49 с. Наборы пересекаются и не суммируются.

По запросу пользователя следующий native-блок не запускается. После завершения
текущего прогона, проверки очистки и локальной фиксации разработка ставится на паузу.
