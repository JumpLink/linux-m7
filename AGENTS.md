# AGENTS.md — linux-m7

Mainline Linux bring-up for the HTC One M7 (`m7ul`). Read `README-m7.md` for the
current hardware and build status.

## Rules

- Keep the imported APQ8064 basis intact; put M7-specific changes in the board
  DTS, `m7_defconfig`, and `tools/m7/`.
- Never store serial numbers, IMEIs, unlock tokens, credentials, user data, or
  private customer information in this repository.
- Do not unlock, flash, erase, or write a partition without an explicit user
  decision. `fastboot boot` is the first hardware test.
- Do not use S-OFF exploits or abandoned unlock services. The supported path is
  the official HTCdev bootloader unlock, which wipes user data.
- Keep the first-boot initramfs read-only toward eMMC. It exposes a root shell
  over USB ACM; that is intentional for a development image, not a daily system.
- Follow `Documentation/process/coding-assistants.rst`. Disclose AI assistance;
  never add a human `Signed-off-by` trailer on the user's behalf.
- New documentation is English. Comments explain why, not what.

## Validation

```sh
BUSYBOX=/path/to/static-arm-busybox ./tools/m7/build.sh
git diff --check
```

A change is not hardware-validated until `fastboot boot` reaches the ACM shell.
Record the exact kernel commit, boot result, and the last visible kernel message.
