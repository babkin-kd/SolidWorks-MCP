# Приёмка clean native CloseDoc dev85

Принят ограниченный scope `native_document_close_clean_v1`: internal12/12
(68.40с), public MCP10/10 (64.92с),
один точный installed wheel без PYTHONPATH. Metadata69 инструментов/20
guarded operations; output schemas и installed provenance подтверждены.
Полный pure перед wheel4673 passed/323 CAD deselected (60,00с).
После исправления external verifier defaults:71 связанных pure passed (0,87с);
итоговый полный пакет4677 passed/323 CAD deselected (60,07с), [контрольная точка](CHECKPOINT_DEV85.md).

## Точная привязка

- Git wheel: `16c2d069ab2c71f8933a4435aa59c7623f3ff511`.
- Source digest: `db138e3e06b37476b8ba03205337dbae6d204850cf1aeb04ebfa2e33defc364a`.
- Wheel: `solidworks_mcp-2.0.0.dev85-py3-none-any.whl`.
- Wheel SHA256: `68e50266a8df62a1ea38e2ba010bc852aa068259d809075998cb3e0725d3ed28`.
- Internal report SHA256: `d14915bfc25bba1dcda7faa9ba3d062a4e3032dcbeb474c603b64ac5a3fd4b8a`.
- Public report SHA256: `59803fd3e6edfb8f3fb90a488c5a67ee10c766364ec207e5a3dd974619e95a4e`.

| Верификатор/fixture/helper | SHA256 |
| --- | --- |
| `verify_native_document_close.py` | `6da6078b3f366fe1e4cfde945162045e43571e2af1a47c324957950f3df34f01` |
| `verify_geometry_reads.py` | `a87bdfc80e1fe2a94b54d26bef56cd92dfd63dffcfd9120d879946f86fb0d4a0` |
| `verify_native_document_save.py` | `daddc53a8f0485cf1268f52be157e7713b460ca210cc226e7215bb873f8130ba` |
| `verifier_lifecycle.py` | `e002f1cc672a8edb44ca700852bf275ee58bec4d6e47757b0c0efe09cd553c32` |

## Фактическое покрытие

По4 успешных durable native CloseDoc в каждом прогоне закрыли по5 собственных
моделей: сборку и явно разрешённую скрытую деталь, чертёж, две детали.
Survivor guard counts3/2/1/0 и полный CIP/selection release проверены по журналу.
Одна explicit activation потребовала подтверждённого UI release при сохранении
CIP/selection scopes; остальные переходы уже соответствовали выбранному survivor.

Реальный dirty сосед не сохранён и не закрыт вместе с другими target-моделями;
его metadata/view/selection/геометрия и disk bytes сохранились. Перед последним
close он отдельно сохранён native fixture setup; это не приёмка first-save/MCP-save.
Полные model/window retirement, all baseline native file fingerprints, режимы,
настройки приложения и empty/free baseline после всех5 закрытий подтверждены.
Non-STL preferences проверены; STL не расширяет scope этой приёмки.

Public10: hidden allowlist, dirty target и surviving assembly reference отказали
до записи; assembly+hidden retirement, request replay без второго close,
invalid retired document ID, stale prewrite revision, active drawing/part и
last clean user-controlled document прошли. Internal отдельно проверил inactive
configuration и foreign document ID. Исходная сборка имела реальный компонент;
incoming reference проверен native, не только fake domain.

Журнал internal: failed=7, succeeded=8; unknown=0, unresolved holds=0.

Журнал public: succeeded=19, failed=5; unknown=0, unresolved holds=0.

## Отказы сохранены отдельно

- Dev83: fixture setup отказал до MCP-close,0 case; own5 exact cleanup,
  jobs отсутствуют. Modern dependency getter на SW2023 возвращал None при
  реальном компоненте; independent live/as-saved/component/view census добавлен.
- Dev84:9 case, затем drawing close/activation unknown. Terminal-аудит подтвердил
  точный retirement и неизменные survivors/files/windows/settings; requested
  activation не совпала. По standing authority current state reconciled,
  две свои детали закрыты, прежний job остался unknown; close/activation не повторены.
- Dev85 internal1 accepted12 на предыдущем verifier hash — исторический receipt.
- Dev85 public1:0 case, verifier default-argument mismatch. Все7 jobs только на
  чтение и терминальны; MCP-close не отправлен. После coherent read-only proof
  остановлены только exact owned controller/server PID, свои5 fixtures закрыты.
  Новый matching-defaults regression проверяет actual facade payload.
- Final internal2/public2 выше имеют одинаковые финальные verifier/helper hashes;
  прежние failures/unknown/прерванные отчёты не заменены успешными.

## Что остаётся

First save/open и полная lifecycle-цепочка S1-15/N6 обязательны; clean unsaved
пока pure-only, dirty-owned discard и retained-reference close не реализованы.
Полный internal data unload не заявляется. Background shutdown/COM throw/
no-effect/release fault пока fake domain/guard, не native-приёмка этих сценариев.
Пять моделей не доказывают масштаб1000+ и все referenced/hidden/virtual состояния.
Другие ранее принятые инженерные операции не становятся same-wheel-принятыми
автоматически. Стадия1 открыта; импорт/экспорт остаются отложенными.

[Контракт](NATIVE_DOCUMENT_CLOSE.md), [матрица](STAGE_1_REQUIREMENTS_MATRIX.md).
