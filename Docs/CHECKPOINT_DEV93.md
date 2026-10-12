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

Полный pure-набор → clean-source commit → один wheel dev93/installed metadata →
positive domain native → N4/N5 с независимыми snapshots/dispatch counts →
public stdio B1. Всё последовательно в одной CAD-сессии, helpers/wheel frozen
до terminal/quiescence. Итоговые данные добавляются по фактическим результатам;
source/interop не переносят автоматически приёмку на новый wheel.

B1–B5 и стадия1 остаются открытыми. L2/L3/S1-B5-ACT scope не расширяется,
imports/export/STL отложены. Нового push/CI нет; локальный пакет накапливается.
