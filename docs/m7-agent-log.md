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
| 2026-11-27 | main implementation session | KOSTENLOS / public | Flash clean Probe 105, run the late live probe and scan from the M7 shell | Completed; `wlan0` appears, netlink and scan work, association waits for credentials |
| 2026-11-27 | main implementation session | KOSTENLOS / public | Trace the SDIO receive corruption with Probes 107 and 108 | Completed; bad headers carry the device MAC shifted by one byte and every transfer falls back to PIO at 1 MHz |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Test the PIO FIFO-drain theory with Probe 109 | Completed; FIFO drains cleanly, short reads show RXACTIVE without RXDATAAVLBL, so the 1 MHz clock is too slow |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Build and test Probe 113 MDP4/DSI0 host bring-up | Completed; stable ACM boot, DSI/PHY/MDP4 bound, late full probe reports WLAN present; DRM card awaits a panel |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Prepare Probe 114 M7 command-mode panel | Completed; corrected PMIC boost pins, deferred revision-specific backlight and added the panel MAINTAINERS entry |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Require a late complete WLAN host probe | Completed; capture repeats the live probe until `wlan0` appears, with 68 Python tests passing |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Build and package Probe 114 | Completed; clean `e6141baf1` image, p6 NVRAM, static WLAN tools and both DTBs validated; hardware test pending |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Diagnose the Probe 114 Pstore crash | Completed; VM initialization failed before the errno was logged, then duplicate KMS cleanup crashed in `destroy_workqueue()`; single-owner teardown fixed |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Harden serial capture across USB reconnects | Completed; stale ACM and transient `EIO` paths retry, probe acceptance resets per connection, and the live Probe 109 host probe passes |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Build and package Probe 115 | Completed; clean `d0396bb1b` image with VM errno diagnostics, p6 NVRAM and no WPA configuration; hardware test pending |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Flash and validate Probe 115 | Completed; complete late host probe reports WLAN present, while MDP4 VM attach fails with `-EBUSY` and no DRM card appears |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Fix MSM IOMMU domain ownership | Completed; release the legacy ARM DMA mapping before MSM attach, with 76 tests and a clean GCC 16 object build; Probe 116 hardware test pending |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Recover and diagnose Probe 116 | Completed; Probe 109 preserved a SHA-verified 1 MiB Pstore dump, exposing recursive legacy DMA cleanup during old-domain teardown |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Fix legacy DMA cleanup ordering | Completed; select direct DMA ops before detach, with 77 tests, clean strict checkpatch and a clean GCC 16 object build; Probe 117 hardware test pending |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Flash and diagnose Probe 117 | Failed before serial/ACM output; no Probe 117-specific Pstore record, so the DMA fix is not hardware-validated and Probe 117 must not be repeated unchanged |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Recover Probe 117 RAM and correct Pstore attribution | Probe 109 restored through TWRP/HBOOT; SHA-verified dump contains Probe 116 in fixed `dmesg-0` and Probe 109 in the moved console ring, not Probe 117 |
| 2026-11-28 | main implementation session | KOSTENLOS / public | Protocol vendor-source analysis | Public `cm-14.1` snapshot pinned; panel mode, rails, first-init/resume order, DCS tables and PWM revision path recorded in `docs/m7-vendor-analysis.md` |

Failed agent runs are kept in the log so a later reader does not mistake a
missing report for missing work.
