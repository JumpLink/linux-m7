# M7 agent log

The main implementation session is **HungerG Free over OpenCode**. It performs
the code changes, hardware tests, reviews and commits.

Subagents are recorded by role and data tier. Exact model IDs are intentionally
not duplicated in this public repository; the workspace maps roles to models in
`opencode.jsonc`.

| Date | Agent role | Data tier | Task | Outcome |
|---|---|---|---|---|
| 2026-11-26 | `scout` | KOSTENLOS / public | Inventory Mainline drivers and rank the next M7 subsystem | Completed; touchscreen had the lowest risk, WLAN the highest headless value |
| 2026-11-26 | `explore` | KOSTENLOS / public | Research M7UL touch, display, WLAN, Bluetooth, battery and audio | Failed twice on a provider tool-result error; no result used |
| 2026-11-26 | `free-scout` | KOSTENLOS / public | Inspect the clean Mainline tree and rank driver candidates | Completed; identified missing board nodes and upstream drivers |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Identify M7UL chips, pins, firmware and board wiring | Completed; confirmed BCM4335 and Synaptics data |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Resolve the SDCC bus and WLAN electrical details | Completed; confirmed eMMC on SDCC1, WLAN on SDCC3 and 2.8-2.9 V card power |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Check NVRAM sources | Completed; no public M7-specific NVRAM found |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Check the 32 kHz pin and WLAN power sequence | Completed; GPIO 43 has no software consumer in the published M7 tree |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Trace Downstream F1 activation and ChipClkCSR setup | Completed; no separate host mode identified, exact claim path under follow-up |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Resolve PM8921 GPIO 43 function | Completed; 32 kHz output is plausible, `func2` remains unconfirmed |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Resolve the exact Downstream F1 claim path | Completed; Downstream uses host claim plus `sdio_enable_func()` and CCCR IOEx/IORx, with no already-enabled skip |
| 2026-11-26 | `free-coder` | KOSTENLOS / public | Resolve Downstream SDCC3 width, clock and power setup | Completed; identified 4-bit platform data, L6/L7 regulators, `WL_REG_ON` configuration and the MSM clock sequence; main session verified the code and tested each relevant difference |
| 2026-11-26 | `go-flash` | GO / private docs | Update the hub workbench document | Rejected because the OpenCode Go monthly limit was reached; main session made the edit |
| 2026-11-26 | `free-scout` | KOSTENLOS / public | Reconstruct the port history from public commits | Completed; chronology cross-checked against the main session record |
| 2026-11-27 | `general` | KOSTENLOS / public | Retry public M7 WLAN, SDCC3 and NVRAM source research | Completed; public note written, primary-source claims still checked by the main session |
| 2026-11-27 | `free-coder` | KOSTENLOS / public | Locate CR4, firmware callback, F2/IRQ, control and attach trace points | Completed; main session verified the call sites and added probe-only `M7_WLAN_TRACE` markers |
| 2026-11-27 | `go-flash` | GO / private code | Diagnose the Probe 89 control-response timeout from the local trace and driver call sites | Rejected because the OpenCode Go monthly limit was reached; no report used, main session continued |
| 2026-11-27 | main implementation session | KOSTENLOS / public | Add reproducible static ARM WLAN tools and credential-safe image packaging | Completed; 43 tests and two identical builds pass, hardware association is pending |

Failed agent runs are kept in the log so a later reader does not mistake a
missing report for missing work.
