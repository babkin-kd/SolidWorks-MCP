# Конечный чек-лист dispatch preview/delete dev97 — 14.10.2026

Пассивный аудит исходников; native/COM, серверы и проверочные процессы не
запускались. Это подготовка, а не фактический gate. Исходный статус очереди:
positive1 принят, faults1 pending, три N5 и public `not_run`.
Актуальное состояние подтверждает единственный native-владелец.

Точный кандидат: `2.0.0.dev97`, build
`49b899c9c6048c89be81e20c9c5c29f0e4ee50d4`, wheel SHA256
`702b7e18c9cafaafb14f8ca800ff4c3c361d44ed87abeb8d87e01df6992c382b`.
Приёмка dev96 не переносится. Установленный dev-пакет проверяется без source
PYTHONPATH; рабочая v1 сохраняется.

## Условия перед каждым dispatch

- [ ] Нынешний владелец действительно завершил процесс: terminal отчёт,
  normal exit, `native_calls_live=false`, отсутствие pending native/ledger
  флагов и retained STA/process. Отдельный промежуточный `false` недостаточен.
- [ ] Подтверждены actual SQL, собственная очистка, пустой список owned
  documents, полный исходный/restored baseline и application; служебные
  флаги и предусмотренная область preferences восстановлены. Очистка только
  собственных документов после завершения вызовов; неизвестные задания не
  повторять и не согласовывать автоматически.
- [ ] Фактический exact positive/fault gate прошёл по конечным отчётам,
  их SHA, родительским `report.json`, текущим helper hashes и SQLite в режиме
  read-only. N5 запускается после faults gate по этой очереди, хотя его CLI
  автоматически проверяет только positive. Historical faults unknown остаётся
  `unknown/unresolved`, `reconciliation=None`, application hold сохранён в
  прежнем журнале; этот журнал не переиспользуется для следующих прогонов.
- [ ] Wheel/version/build/installed origin совпадают; state каждого следующего
  случая — новый, ещё не существующий дочерний каталог частного `work/`.
  Не создавать его заранее. Полные отчёты, журналы, CAD и equation file вне Git.
- [ ] Порядок только последовательный: `child_plane` → `unused_equation` →
  `linked_equation` → public. Между случаями повторить terminal/cleanup gate.
  Любой unknown/pending/setup failure прекращает зависимую очередь.

## Конечные случаи и доказательства

| Случай | Точные labels / ожидаемый отказ | Обязательное свидетельство |
| --- | --- | --- |
| Faults prerequisite | `leaf_stale`, `leaf_foreign`, `leaf_no_effect`, `leaf_observation_unknown`, `leaf_unknown_new_request_blocked` | Все пять `passed=true`; actual SQL и неизменные replay; no-effect rolled_back; unknown unresolved без reconciliation; новый запрос blocked; physical own cleanup и baseline, exact positive reference |
| `child_plane` | `n5-child_plane-fixture-setup`; `n5-child_plane-preview`, `n5-child_plane-execute`, каждый с replay; `leaf_deletion_unsupported` | Setup succeeded/committed до запросов; 12 парных ledger rows: `impact_child_plane_` + `set_first_reference_mark`, `select_face`, `insert_plane`, `clear_owned_selection`, `rebuild`, `rename_plane` |
| `unused_equation` | `n5-unused_equation-fixture-setup`; `n5-unused_equation-preview`, `n5-unused_equation-execute`, каждый с replay; `first_save_snapshot_unsupported` | Setup succeeded/committed; 4 парных ledger rows: `impact_unused_equation_` + `add_unused_global`, `rebuild` |
| `linked_equation` | `n5-linked_equation-fixture-setup`; `n5-linked_equation-preview`, `n5-linked_equation-execute`, каждый с replay; `first_save_snapshot_unsupported` | Setup succeeded/committed; 8 парных ledger rows: `impact_linked_equation_` + `add_unused_global`, `set_file_path`, `link_file`, `rebuild`; owner-created private file identity/mtime/ctime/bytes/SHA неизменны до/после setup и requests |
| Public | `B2-public-depth12-full9600`; `B2-public-Russian-name-same-reference`; `B2-public-suppress-full-state`; `B2-public-return-full-state`; `B2-public-leaf-preview-delete-replay-retired-ID` | Все пять `passed=true`; 12 мм / 9600 мм³, русское имя, opaque ID/native mapping, full independent observer, actual SQL/replay, retired ID/PID, сохранный эскиз/сосед, supervised cleanup и baseline |

Для каждого N5 дополнительно: исходная durable B1 sketch/extrusion lineage и
BASE preparation на исходном owner/epoch/PID; полные равные текущие сессии,
неизменный сосед, original creation jobs/receipt; whole-request event envelope
обоих документов исключает ABA. Четыре вызова — preview, replay, execute,
replay; два первых отказа добавляют только свои SQL rows без checkpoint,
оба replay ничего не добавляют и не dispatch. Domain calls ровно
`preview=1, execute=1`; application hold clear в свежем журнале.
Setup failure запрещает preview/delete и дальнейшие наблюдения при uncertainty.

N5 принимается только при `b2-impact-report.json`: `phase=terminal`,
`fixture_case_passed=true`, `accepted=true` для этого случая, actual parent
SHA/terminal/cleanup/baseline и terminal SQL. `native_b2_accepted` и
`public_mcp_accepted` остаются false. Public проверяет все captures returned и
final full state; его `public_positive_case_passed=true` также не закрывает B2.

## Команды-шаблоны для единственного владельца

В PowerShell из `C:\Codex\MCP Solidworks`; выполнять только после gates выше.
`$DevPython` — проверенный python.exe установленного dev-окружения;
`$Wheel` — фактический wheel кандидата; `$PositiveReport` — частный
`leaf-positive-report.json`, `$FaultsReport` — частный `leaf-faults-report.json`;
`$PositiveSha`/`$FaultsSha` — SHA256 конечных файлов, не родительских отчётов.
`$ChildState`, `$UnusedState`, `$LinkedState`, `$PublicState` — четыре разные
свежие абсолютные папки внутри `work/`. Переменные заполняет владелец по
действительным артефактам; эти шаблоны не присваивают вымышленных путей/SHA.

```powershell
& $DevPython scripts/verify_b2_impact_native.py --fixture-kind child_plane --positive-report $PositiveReport --positive-report-sha256 $PositiveSha --run-solidworks --state-dir $ChildState --wheel $Wheel --expected-version 2.0.0.dev97 --expected-git-sha 49b899c9c6048c89be81e20c9c5c29f0e4ee50d4
```

После фактического terminal/cleanup child_plane:

```powershell
& $DevPython scripts/verify_b2_impact_native.py --fixture-kind unused_equation --positive-report $PositiveReport --positive-report-sha256 $PositiveSha --run-solidworks --state-dir $UnusedState --wheel $Wheel --expected-version 2.0.0.dev97 --expected-git-sha 49b899c9c6048c89be81e20c9c5c29f0e4ee50d4
```

После фактического terminal/cleanup unused_equation:

```powershell
& $DevPython scripts/verify_b2_impact_native.py --fixture-kind linked_equation --positive-report $PositiveReport --positive-report-sha256 $PositiveSha --run-solidworks --state-dir $LinkedState --wheel $Wheel --expected-version 2.0.0.dev97 --expected-git-sha 49b899c9c6048c89be81e20c9c5c29f0e4ee50d4
```

После принятия всех трёх N5 на этом wheel, их terminal/cleanup и actual
positive/fault gate:

```powershell
& $DevPython scripts/verify_b2_public.py --run-solidworks --positive-report $PositiveReport --positive-report-sha256 $PositiveSha --faults-report $FaultsReport --faults-report-sha256 $FaultsSha --state-dir $PublicState --wheel $Wheel --expected-version 2.0.0.dev97 --expected-git-sha 49b899c9c6048c89be81e20c9c5c29f0e4ee50d4
```

## Расхождения автоматических gates

- `verify_b2_impact_native.py` не принимает faults arguments: exact faults gate
  и освобождение прежнего владельца нужно подтвердить отдельно; не добавлять
  вымышленные `--faults-report` или `--wait-timeout` к этому CLI.
- `verifier_b2_public_preflight.py` имеет функцию `preflight(args)`, а не CLI.
  Она проверяет positive/fault reports, SQL/helpers и installed metadata83/27,
  но не три N5 reports; возвращает открытый
  `B2-N5-dependent-linked-impact`. Полный preflight включает installed metadata
  provider и не является разрешением запустить его параллельно занятому owner.
- `verify_b2_public.py` выполняет finite N1–N4 public positive route; успешный
  public не подтверждает публичную N5 refusal chain автоматически. N5/public/B2
  acceptance нужно различать, `not_run` никогда не засчитывать как passed.
- В исходной очереди фраза «positive/fault gates ещё ожидаются» выше таблицы
  отстаёт от строки принятого positive1; текущий audit не меняет эти статусы.

Источники: [очередь](B2_DEV97_REMAINING.md),
[N5 CLI](../scripts/verify_b2_impact_native.py),
[public CLI](../scripts/verify_b2_public.py),
[public preflight](../scripts/verifier_b2_public_preflight.py).
