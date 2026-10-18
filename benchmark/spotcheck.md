# Call-graph spot check (15 functions)

Method: `scripts/callgraph_spotcheck.py` samples 15 of 849 non-test functions (seed 42). Each function's graph callers were compared against a text search of a local clone of borgbase/vorta (`src/` and `tests/`), reading the matching lines by hand. Run on 2026-10-18.

| # | Function | Graph callers | What the code shows | Verdict |
| --- | --- | ---: | --- | --- |
| 1 | `SchedulerState.record_finish` | 1 | `execution.py:118` calls `self.scheduler.record_finish`; the wrapper delegates via `self._state` (`scheduler/__init__.py:147`) | Real caller found; wrapper-to-state edge missing |
| 2 | `VortaApp.check_darwin_permissions` | 2 | Same two call sites | Match |
| 3 | `network_manager.get_result` | 3 | Module function at `network_manager.py:217`; `kwallet.py` has a separate method of the same name | Match |
| 4 | `PasswordLineEdit.toggle_visibility` | 1 | Same call site | Match |
| 5 | `ExtractDialog.slot_sorted` | 0 | `extract.py:91`: `.sorted.connect(self.slot_sorted)` | Qt signal, not a call |
| 6 | `AddProfileWindow.button_validation` | 0 | `profile_add_edit.py:25`: `.textChanged.connect(...)` | Qt signal, not a call |
| 7 | `AddRepoWindow.encryption_listener` | 0 | `repo_add.py:147`: `.currentIndexChanged.connect(...)` | Qt signal, not a call |
| 8 | `config.init_dev_mode` | 1 | `__main__.py:59` and `63` in the body of `main` | Match |
| 9 | `PasswordInput.set_error_label` | 5 | Same five callers | Match |
| 10 | `utils.get_directory_size` | 1 | Same call site | Match |
| 11 | `VortaScheduler/SchedulerState.record_skip` | 2 | `execution.py:64,103`, `scheduling.py:241`; wrapper delegates via `self._state` (`__init__.py:139`) | Real callers found; wrapper-to-state edge missing |
| 12 | `error_state` | 0 | A property (`@error_state.setter`), accessed as an attribute | Not a call |
| 13 | `is_system` | 0 | Read as an attribute (`abc.py:41`, `borg_job.py:191`) | Not a call |
| 14 | `parse_args` | 2 | Same two call sites | Match |
| 15 | `__init__` | 0 | 55 call sites; constructor calls are not linked to `__init__` | Constructors not modelled |

## Tally

- 7 of 15: graph callers agree with the code.
- 2 of 15: real callers found, but a delegation through `self._state.x()` is not resolved.
- 3 of 15: zero callers because the function is connected as a Qt signal slot.
- 2 of 15: zero callers because the code has no call (property, attribute read).
- 1 of 15: constructor.
- No caller returned by the graph was absent from the code in this sample.

## Other checks

- Hand-picked: `is_worker_running`, `set_timer_for_profile`, `_simplify_filter`. All 14 call sites found in the code appear in the graph's caller lists, with no extra callers.
- All 72 `__init__` methods in the graph have zero callers.
- Same-named methods in different classes share callers: the three `notifications.deliver` methods each list the same 6 callers. All 6 really call `notifier.deliver(...)`, so no caller is invented, but the graph cannot tell which class each call reaches.

## Limits

15 functions is a small sample and the text comparison is by hand, not an execution trace.
