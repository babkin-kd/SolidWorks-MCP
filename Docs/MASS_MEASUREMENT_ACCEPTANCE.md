# Приёмка публичного измерения массы — dev71

11.10.2026. **Принято в области детали**: internal22/public6 accepted=true на
одном чистом установленном wheel; SolidWorks2023, revision31.2.1. Стадия1
остаётся открытой. Сборки/custom frames/bounds/distance и общий N0–N6 gate
этим результатом не закрываются.

| Идентичность | Значение |
| --- | --- |
| Пакет | 2.0.0.dev71 |
| Git SHA исходников wheel | c99ab505b26903bf0c59ce44e12b76afe5a4c960 |
| Source digest | 8dd0160b2621bdec731d6f8f9dc1184b081f116b077d531efef40ebab219b1af |
| Wheel SHA256 | bb14fd79e653ff45286e17f18f56e0229fe2f41f31eaaab467e804512df2412c |
| Полный pure | 4072 passed /323 CAD deselected,53,24с; deselected не являются CAD-успехом |
| Installed console metadata | 51 инструмент/18 guarded операций; accepted=true,без CAD |

Два инструмента: measurement_prepare_mass/measurement_get_mass,
scope part_mass_selection_measurement_v1. Модель не редактируется;
временные UI effects защищаются durable application checkpoint. Числовой
fingerprint геометрических моментов12 значащих цифр; сильные native identities
и observation проверяются на обеих границах. [Контракт](MASS_MEASUREMENT_V2.md).

## Что проверено физически

Внутренний native-стенд использовал домен и реальный journal/guard установленного
пакета: два solid-тела и поверхность; все тела и каждый выбранный solid;
foreign/inactive/stale/surface отказы; hidden body inclusion/explicit scope;
возврат исходного UI-selected другого тела; мм и дюймовые настройки документа
при результате в мм/кг; другая конфигурация с одним телом и отказ чужой
configuration reference; suppressed/deleted body refs и восстановленная
геометрия; document mass/center overrides rejected, возврат расчётных значений
после изменения исключительно собственных fixtures. Всего22 случая.

Публичный stdio/MCP-стенд проверил6 случаев: все solids; request_id replay без
второго расчёта; выбранное второе тело; stale before-write; foreign body
before-write; восстановление UI selection другого тела. Вызовы с timeout0
наблюдались до terminal через job_get. Полный подробный native-набор не
дублировался в публичном стенде. OutputSchema/каталог/build проверены отдельно.

В успешных измерениях guard release доказан: исходный CommandInProgress=False,
собственное acquisition/release; model lock0→2→0; selection_preserved=True.
Overrides дают известный failed/rolled_back с read-only доказательством
исходного состояния, без повторения Resume/расчёта. Собственные fixtures
закрыты без сохранения; пуст/free baseline и non-STL-настройки восстановлены.

Hold при неподтверждённом восстановлении, переживающий restart/reconnect,
доказан **искусственным доменным сценарием**. Реальный native unknown/restart
и совокупный N4 здесь не проводились, S1-10/11 остаются открытыми. Назначение
материалов предприятия не проверялось, плотность — эффективная SolidWorks.

## Точные локальные свидетельства

CAD/SQLite/полные отчёты остаются вне публичного Git. Ниже ссылки-идентификаторы
приватных файлов, хеши позволяют сопоставить опубликованное описание.

| Отчёт | SHA256 |
| --- | --- |
| work/native-mass-guard-dev71-1/report.json | 7b0095be353f82eb1582c95d2f4a801a0839f9dfeba72b50c9d8fb52a3b9d3e2 |
| work/native-mass-mcp-dev71-2/report.json | 66ee8b9c9c4bd508b76c3e32df0dfe07609750929364d1581b0fe844fa06ff0b |

Internal verifier SHA256:1f21403b5b471269f4592f556d813d2552c84afe1d80fe36ed3d1871caab0f2a.
Public verifier SHA256:b88c58c4f6417be6118f6534094a486821ee95018460d1bfbcf8b890c0357cb0.
После исправления внешнего public harness прошли18 связанных lifecycle/стендовых
тестов; source/package wheel не менялся, полная пересборка не требовалась.

## Неуспешные попытки сохранены отдельно

Dev70 internal: pre-write/stale из-за one-ULP разницы (~1,6·10⁻²⁷ кг·м²);
ошибка обработки отсутствующего checkpoint в стенде. Ни одного расчёта;
accepted=false. Независимое read-only сравнение подтвердило совпадение native
identities и точную причину. Terminal собственные fixtures закрыты после
проверки отсутствия mutation/holds. Dev71 исправил fingerprint, прошёл новую
полную pure/build/installed/native-приёмку.

Dev71 public попытка1: ошибка аргумента контекста во внешнем стенде, до первого
расчёта. Два read jobs succeeded, никаких mutations/holds; accepted=false.
После SDK shutdown exact-owned terminal cleanup подтверждён. Исправление
только harness, свежий журнал попытки2 принят на том же wheel.

GitHub push/CI не запускались. Рабочая v1 сохранена, wheel установлен в .venv
без PYTHONPATH исходников. Приёмка не является утверждением о всех прежних
CAD-scopes на новом wheel или завершении стадии1.
