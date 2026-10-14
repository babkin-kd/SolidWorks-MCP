# Публичное измерение массы — стадия 1

Кандидат dev71 добавляет measurement_prepare_mass/measurement_get_mass и
part_mass_selection_measurement_v1. Каталог51 инструмент/18 guarded операций;
measurement.mass относится к guarded UI effects, геометрия не редактируется.
Dev71 принят:4072 pure/323 CAD deselected, metadata51/18, internal22/public6
accepted=true на одном wheel; cleanup/baseline подтверждены.
[Точное свидетельство](MASS_MEASUREMENT_ACCEPTANCE.md). Историческая internal
dev34 не является приёмкой этого фасада.

Явные документ, активная конфигурация, observation revision и необязательный
persistent body_id: все solid-тела, включая скрытые, или одно заданное тело.
Surface исключены; solid membership и roundtrip каждого тела проверяются.
Лимит500 тел. Model frame, мм³/мм²/кг/кг·м⁻³, центр в мм. Эффективная плотность
берётся из SolidWorks; назначения материалов предприятия не проверяются.
Актуальные document/scoped mass/center overrides запрещены; они не сбрасываются.
Assemblies/custom frames/bounds/distance остаются остатками S1-16/S1-06.

Preparation не меняет UI. Ревизия связывает body membership/geometric moments
GetMassProperties(1.) с числовым fingerprint12 значащих цифр и исходный PID/mark roster выделения; сильные native
identities удерживаются на одном STA на время задания. Не является полной
ревизией редактирования геометрии или сертификатом неизменности материалов.
Неподтверждённые PID выбранных UI objects отвергаются до записи.

После durable application checkpoint guard получает собственный CommandInProgress
и lock точной модели0→2→0. Он не создаёт внешнего SuspendSelectionList:
сама mass calculation использует ровно одну пару Suspend/Resume. Validate,
postconditions и проверка release сохраняют исходные objects/marks. Busy flag
не заимствуется; другой документ не активируется скрыто. Известный отказ при
доказанном возврате — failed/rolled_back. Restore ничего не пишет и не повторяет
Resume/расчёт. Неполный возврат — unknown/application hold, переживающий restart
и новую connection epoch; обычная очистка не превращает задание в success.

request_id/replay/conflict и timeout следуют общему job protocol. timeout0
даёт operation_id для job_get; завершение ожидания не отменяет COM.

Проверки блока: связанные domain/native-shaped/runtime/facade pure tests;
полный pure перед wheel; installed metadata; verify_mass_properties.py
--guarded-public-domain (подробные22 CAD-сценария) и verify_mass_mcp.py
(public stdio цепочка без повторения всей detailed матрицы).
Все финальные native/installed результаты должны принадлежать одному точному
wheel и иметь terminal/ownership/cleanup доказательства.

Native dev70 остановлен pre-write/stale: повторный moment read отличался
на один binary ULP (~1,6e-27 кг·м²), identities совпадали. Dev71 нормализует
fingerprint12 значащих цифр; observation и strong membership сохраняются
на обеих границах. Это измерительная точность fingerprint, не универсальное
доказательство неизменности BREP. Около границы округления возможен безопасный
ложный stale; неподтверждённое действие автоматически не повторяется.
