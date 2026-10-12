# Кандидат dev93: сохранение вида и native-постусловия отдельного выдавливания

Цель возобновлена после пользовательской паузы. Последний dev92 positive
завершился failed; historical extrusion unknown сохранён, hold reconciled
только после независимой quiescence и собственных CloseDoc с полным baseline.
Старый request не повторяется. [Предыдущая контрольная точка](CHECKPOINT_DEV92.md).

## Исправления по сохранённым доказательствам

Detached replay фактического dev92 checkpoint/readback выявил три расхождения:
автоматический isometric/zoom первого тела, inactive ThinWallType=-1 и дополнительные
подтверждённые parent links от той же плоскости и начала координат к extrusion.

1. Исходный target model view сохраняется в native receipt с canonical model/view
   identity. Под тем же guard однократно возвращаются Orientation3, Scale2 и
   Translation3, только если изменились. Используются double SAFEARRAYs; созданные
   MathTransform/MathVector и полный конечный readback проверяются точно. Каждая
   запись имеет pending/returned journal pair. Lost ack, storage или readback
   uncertainty удерживают эффект и запрещают blind inverse/retry.
2. Постусловия допускают ровно inactive ThinWallType=-1/0 при IsThinFeature=False,
   нулевой толщине обеих стенок и cap, без link/draft/reverse и с полным solid BREP.
   -1 — наблюдение SW2023, не объявленное значение thin-wall enum. Документация
   [ThinWallType](https://help.solidworks.com/2019/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IExtrudeFeatureData2~ThinWallType.html?format=P&value=)
   описывает эту настройку для thin base; признак отсутствия thin feature проверяется
   отдельно [IsThinFeature](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IExtrudeFeatureData2~IsThinFeature.html).
3. Дополнительные direct parent links разрешены лишь для independently bound
   plane/origin заимствованного эскиза, уже имеющих подтверждённую baseline связь
   с ним. Parent/child census совпадает, старые ссылки сохраняются, absorbed link
   только owned extrusion→borrowed sketch. Произвольные ancestors не допускаются.

Точные view setters подтверждены официальными свойствами
[Orientation3](https://help.solidworks.com/2025/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelView~Orientation3.html),
[Scale2](https://help.solidworks.com/2010/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelView~Scale2.html)
и [Translation3](https://help.solidworks.com/2021/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelView~Translation3.html).
Read-only getters на соседях/полные геометрические proofs не ослаблены; view не
включён в volatile fields. Новых инструментов/профилей/режимов не добавлено.

## Доказательства до итоговой сборки

- Related extrusion/postconditions: **95 passed /1,49 с**.
- Related bridge/executor/native-step journal: **161 passed /3,10 с** с перекрытием
  предыдущего набора. Related view/protocol/supervisor: **235 passed /28,90 с**.
  Это pure/domain evidence с искусственным CAD, не native-приёмка.
- Short interop на установленном dev92, typed setters: **terminal/accepted**,52
  pending/returned rows, own_count0, полный baseline/non-STL восстановлен;
  view совпал до и после release. SHA256 private report
  `1ee5b64dcfd118db88163a121299eb50b3157252f55309e230c1b54f7b4ff126`.
  Это проверка зарегистрированных COM-сигнатур и inverses, не приёмка dev93/B1.
- Первая short попытка с untyped Python-list выявила неверный Translation3
  readback. Все её вызовы вернулись; собственная единственная fixture закрыта
  после независимой проверки с полным исходным baseline. Не засчитана passed.
- Detached replay сохранённого dev92 стал admitted лишь при диагностической
  подстановке сохранённого исходного view. Это условное объяснение дефекта,
  исходный failed report/unknown не переписан и не объявлен успешным.

Новый public driver готовит одну конечную stdio-цепочку на exact installed wheel,
после strict same-wheel positive/N4/N5 preflight. Создание документа связывается
через committed opaque ID/receipt, unchanged same-connection preparation,
ID-bound HWND и независимую canonical identity; creation DTO сам HWND не содержит.
Публичные отрицательные physical cases не дублируют внутренний N4/N5.
Full SQL row сверяется с job_get published projection без единственного private
digest; сам digest пересчитывается и проверяется. Независимые av_UUID namespaces
сравниваются через bijection полных view rows и assigned axis partitions; внутри
root adapter EMPTY→SKETCH→BASE сохраняются реальные local view identities и
borrowed bindings. Остальные поля snapshot сравниваются точно. Related public:
**213 passed /23,76 с**, включая64 новых случая; tests artificial/SQLite, не CAD.
Отдельный durable unknown/hold/no-retry при unconfirmed view проверен в related
execution32/1,60 с. Наборы перекрываются и не суммируются.

Internal drivers дополнительно сохраняют HWND/metadata нормально возвращённых
собственных fixtures до дальнейших операций. Эти данные дополняют retained
canonical COM ownership, а не разрешают adoption по имени или roster delta.

## Следующие конечные gates

Полный итоговый source pure-набор: **6824 passed /323 CAD deselected /163,45 с**,
exit0. Private log `work/pytest-dev93-full-1.log`. CAD cases в этом запуске
исключены и не засчитываются passed. Исполняемые файлы после этого набора
не менялись; агент завершён, интеграцией и native по-прежнему управляет root.

## Точный установленный wheel и текущая native-проверка

- Версия `2.0.0.dev93`, clean build Git
  `5710f6395c84ecff01d014fffafe932d2c66b797`.
- Source digest `f87391ff089daf16f79da1be075d22b69d6a215f9d4d37cac97a148f1ad993e0`.
- Wheel SHA256 `af09a868c8718ac74a44dda6f807edb59a7179206bd48a78281e1435cead6a4e`.
- Offline artifact и installed metadata/stdio приняты, **79 tools /25 mutations**;
  никакие CAD tools при metadata-проверке не вызывались. Установка только в
  проектной dev .venv; рабочая v1 сохранена. Source PYTHONPATH отсутствует.

Private evidence: `work/wheel-dev93-report-1.json`,
`work/metadata-dev93-report-1.json`, wheel в `work/wheels-dev93/`.
Positive domain driver запущен в свежем state
`work/native-rectangle-dev93-positive-1`; unified session **15395**.
Один CAD-владелец, новый connection/request scope; старый unknown не повторяется.
Wheel/десять positive helpers фиксированы до terminal/quiescence. Running не
засчитывается как accepted и не разрешает следующий N4/N5/native/public запуск.

Промежуточный фактический результат этого same-wheel прогона: отдельный sketch
и replay прошли, job succeeded/committed,22 строки/11 пар pending→returned. Строгий detached
journal gate повторно подтвердил весь job; независимый native snapshot показал
`closed_rectangular_sketch_v1` и solid_body_count0, сосед сохранён. Драйвер
перешёл к extrusion preparation. Этот промежуточный статус заменён итоговым
positive-результатом ниже; N4/N5/public и весь B1 ещё не приняты.

## Фактический positive domain native результат

Exact installed dev93 positive завершён **exit0/terminal/positive_case_passed=true**,
**3977,95 с**,75 snapshot captures returned. Приняты четыре конечных labels:
separate sketch/replay, separate extrusion/replay, независимый exact base/dirty
neighbor и собственная cleanup/baseline. Независимый объём
**8000,000000000001 мм³**, один native solid40×20×10 мм. Оба committed jobs
прошли строгие full checkpoint/geometry/guard/ledger gates, русский naming и
borrowed sketch сохранены. Source/short interop результаты этим не подменялись.

Оба собственных документа закрыты, owned_documents=[], native_calls_live=false;
полный original baseline/application/non-STL preferences восстановлен. Terminal
процесс завершился штатно, retained/unknown отсутствует. Независимый passive
positive gate подтвердил wheel и все десять actual helper hashes.
Private report SHA256:
`1645ad860d6394c07a3435a99e4d84802ff585822aaaa2aeb8af3965cbc7085b`;
`work/dev93-positive-preflight.json` accepted. Сам gate сохраняет
`native_b1_accepted=false`: finite N4/N5 и public stdio ещё обязательны.

После terminal/exit0 и проверки positive gate запущен единственный N4/N5
процесс: `work/native-rectangle-dev93-faults-1`, unified session **36515**.
Его preflight потребовал именно этот positive report/wheel/current helper hashes
до CoInitialize/fixture creation. Новые собственные fixtures и state/request;
real COM throw не инжектируется. Helpers этого прогона и wheel фиксированы
до terminal/quiescence. Running не означает passed; public пока не запускался.

Полный pure-набор → clean-source commit → один wheel dev93/installed metadata →
positive domain native → N4/N5 с независимыми snapshots/dispatch counts →
public stdio B1. Всё последовательно в одной CAD-сессии, helpers/wheel frozen
до terminal/quiescence. Итоговые данные добавляются по фактическим результатам;
source/interop не переносят автоматически приёмку на новый wheel.

B1–B5 и стадия1 остаются открытыми. L2/L3/S1-B5-ACT scope не расширяется,
imports/export/STL отложены. Нового push/CI нет; локальный пакет накапливается.

## Пауза по решению пользователя — 12.10.2026

Разработка и новые проверки приостановлены по прямому запросу пользователя.
При проверке состояния unified session36515 подтвердил живой процесс;
native N4/N5 ещё не завершён. В журнале `sketch_positive_prepare` имеет статус
running, последний snapshot capture также running. Поле native_calls_live=false
в промежуточном отчёте не доказывает quiescence всего драйвера.

Фактически пройдены B1-N4-stale-sketch, B1-N4-foreign-plane и
B1-N5-owned-sketch-restoration. Последний job завершён failed/rolled_back;
контролируемая Python-ошибка после возврата native-вызова и полное собственное
восстановление проверены, real COM throw не инжектировался. Весь fault-прогон
по-прежнему accepted=false; остальные случаи и public не приняты.

Две собственные контрольные детали остаются у работающего драйвера.
Внешний CloseDoc и остановка процесса не выполнялись: безопасная очистка пока
не доказана. Уже запущенный конечный драйвер не прерывался и содержит штатную
очистку после завершения своих случаев. После паузы сначала проверить его
terminal/exit, журнал, владение и итоговый baseline; новый native/public прогон
без возобновления разработки не запускать. Wheel и helpers не изменены.

## Возобновление по решению пользователя — 12.10.2026

После команды «Продолжай» проверен тот же session36515: процесс жив, текущий
шаг setup_sketch_job, новый прогон не запускался. Passive audit сохранённых
данных повторно подтвердил строгие prewrite gates двух N4-случаев, нулевые
dispatch counts и точное равенство их полных before/after snapshots; строгий
restoration gate N5-sketch также принят. Все фактические helper hashes
совпадают с замороженным manifest. Private сводка
`work/dev93-partial-fault-preflight.json`; это частичный gate, не приёмка
fault-прогона или B1. Очистка до terminal/quiescence не выполняется.

Один независимый поток готовит только конечную карту оставшейся B3-приёмки,
без COM, тестов и правок исполняемых файлов. CAD и интеграцией управляет root.
