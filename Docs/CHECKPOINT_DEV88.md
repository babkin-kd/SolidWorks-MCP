# Dev88 — кандидат первого сохранения, L3 ещё открыт

Контрольная точка 12.10.2026. Стадия 1 не завершена. L2 принят на прежнем
dev87; его факты не переносятся автоматически на dev88. Приёмка L3 выполняется
по [конечному набору](NATIVE_FIRST_SAVE_ACCEPTANCE.md).

## Точный установленный артефакт

- Версия: `2.0.0.dev88`, build Git `fa4ee2d3233d96b5e5818e39f93253db852c31ba`.
- Wheel: `work/wheels-dev88/solidworks_mcp-2.0.0.dev88-py3-none-any.whl`.
- Wheel SHA256: `420c89cb0acf824e72eb5a8a94019b6a9afd5a2d58d84510426c053984e7076b`.
- Source digest: `74c035faf564dadb1f1e4c25f1f2eb0046c3b3a24ccb14934f60344b2ca71641`.
- `source_dirty=false`; wheel validator accepted=true. Публичная публикация не выполнялась.
- Установлен только в проектную `.venv`; origin — её `Lib/site-packages/solidworks_mcp`.
  Рабочая установка v1 сохранена.
- Installed metadata/stdio accepted=true: 73 tools/22 mutations, output schemas
  и встроенный каталог согласованы. Source PYTHONPATH отсутствовал; CAD не вызывался.
  Отчёт: ignored `work/metadata-dev88-report-1.json`.

## Проверки и ограничение результата

Итоговый source pure: **5978 passed, 323 CAD deselected, 99,46 с**.
Связанный preflight/protocol/metadata-набор: **40 passed, 6,25 с**.
Первый full dev88 имел один packaging failure: версия registry template
оставалась dev87. Исправлено и проверено повторным full-набором; первый failed
журнал сохранён. Private logs: `work/pytest-first-save-dev88-full-1.log` и `-2.log`.

Полная предшествующая **source** domain-проба2 прошла за994,58 с:
committed, 24 native ledger rows, независимый full readback/mapping41,
dirty сосед и собственная очистка/baseline. Это не native-приёмка данного wheel;
[факты и прежний unknown](NATIVE_FIRST_SAVE_PROGRESS.md) сохранены отдельно.

**Installed L3-I1 прошёл**, 1008,63 с, private report
`work/native-first-save-dev88-positive-1/report.json`: positive_case_passed=true,
job succeeded/committed, 24 ledger rows verified, full independent readback,
mapping41, own cleanup/baseline, owned=[], native_calls_live=false. SHA256:
`5deea52c0076a49919213c3f8fd3aeb5a09460887cd61bd53ae690847db817fa`.
Отдельная detached-проверка подтвердила журнал, wheel SHA и совпадение всех
текущих trusted verifier hashes. **accepted=false относится ко всему L3**:
положительный случай не закрывает остальные условия.

**Installed L3-I2 прошёл**, 686,00 с, в `work/native-first-save-dev88-rejections-2/`:
три конечные строки passed — existing destination prewrite, реальный rename→stale,
own cleanup/baseline. Оба отказа до Copy (ровно ноль вызовов), foreign marker
сохранён; trusted verifier hashes и wheel SHA проверены отдельно. SHA256 отчёта:
`247ff1e29613a1f5da851fdb53a6ff936eb4e35bc5489682a8c2dcf6065430fc`.
Первый запуск остановился сразу после нормального создания одной пустой part:
COM IUnknown ошибочно попал в JSON-отчёт, до first-save/stale jobs. Терминальный
процесс завершился; independent inspection и отдельная owner cleanup подтвердили
единственную неизменную чистую пустую контрольную part, закрытие и исходный
empty baseline/CWD/non-STL/CommandInProgress=false. Отчёты первого сбоя сохранены
в `work/native-first-save-dev88-rejections-1/`, включая `owner-cleanup.json`;
ошибка не засчитана как native passed. Проекция теперь содержит только scalars,
normal creation DTO пишется отдельно; 15 связанных pure-регрессий passed (0,60 с).
Fault harness/domain-набор: 95 passed (12,50 с), CAD искусственный.
Незавершённый COM не отменять и не повторять по тайм-ауту наблюдения.

**Installed L3-I3 прошёл**, 874,27 с, private report
`work/native-first-save-dev88-race-1/report.json`: два finite cases passed,
known rolled-back collision, Copy/open-stage/close-stage/publication ровно по одному,
replay без повторного эффекта, foreign bytes/identity сохранены, staging empty,
исходные модели и own cleanup/baseline подтверждены. SHA256 отчёта:
`e895b934220fef21cac9a03a790c16ad50a60f1aa8788cc564f81b9f90570525`.
Detached receipt predicate, exact wheel SHA и current trusted helper hashes
проверены отдельно. Copy/readback/NT no-replace настоящие; инъекция относится
только к producer чужого файла. Predicate/harness проверены 18 связанными
pure-тестами (2,84 с), на искусственном CAD/FS. Source/wheel не менялись;
повторная сборка или широкий pure-набор для новых внешних верификаторов не требуются.

**Installed L3-I4 warning_after_copy прошёл**, 757,28 с, private report
`work/native-first-save-dev88-fault-warning-1/report.json`: три finite cases passed,
unknown/unresolved после инъекции, replay без второго Copy, новый request заблокирован;
released guards, независимый full clone/41-role readback, source/dirty сосед и
staged bytes сохранены. Own cleanup/empty baseline подтверждены. Exact internal
accept-current-state reconciliation снял hold; исторический status остаётся unknown.
SHA256 отчёта: `5e1a0fbf9add4d93c0774e3982cf098906478eeade64621c4c4100a18e304d34`.
Wheel SHA и current trusted helper hashes проверены отдельно. Настоящий normal
Copy receipt True/0/0 записан до warning моста: это **не actual native COM warning**.
**Installed false_after_copy прошёл**, 756,52 с,
`work/native-first-save-dev88-fault-false-1/report.json`: три finite cases passed,
original normal Copy True/0/0, unknown/hold/replay, independent full clone41,
source/dirty сосед, stage retention, own cleanup/empty baseline и exact hold
reconciliation. Historical status остаётся unknown. SHA256:
`bf89c0e9340b3b62ba423668d65b2e2b03c55e1a65ef8eee74236a924d0fa590`.
Wheel/current helper hashes проверены отдельно. Это controlled bridge false,
не actual native COM false. `throw_after_copy` запущен в
`work/native-first-save-dev88-fault-throw-1/`; incomplete/public остаются; L3 открыт.

При подготовке публичной цепочки подтверждён S1-B5-ACT: open сохраняет исходный
active dirty сосед, а dimension edit требует активного target. Публичный explicit
active-part шаг для минимального сценария ещё не реализован. Ручную активацию
нельзя засчитать как всю MCP-цепочку; L2 scope не меняется. Точная ограниченная
задача и приёмка записаны в STAGE_1_BLOCK_ACCEPTANCE.md.

## Остаток

1. L3-I1 завершён на exact installed dev88; сохранять его witness/hash binding,
   не объявляя whole L3 или same-wheel выпуск принятым.
2. L3-I2/I3 завершены. Выполнить конечные L3-I4:
   классификация отказов/hold/replay и восстановление. Инъекцию моста отличать
   от actual native false/warning/throw.
3. Выполнить L3-P1 публичную same-wheel MCP-цепочку с close/open/следующим Save3.
4. Только после этих условий закрыть L3 и перейти к S1-B1…S1-B5; три стадии
   сохраняются. Новый push/CI пока не выполнялись; изменения накапливаются локально.
