// SPDX-License-Identifier: GPL-2.0-only
/* Reboot through the Linux API so the reboot-mode driver receives "bootloader". */

static long syscall4(long number, long a0, long a1, long a2, long a3)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r2 __asm__("r2") = a2;
	register long r3 __asm__("r3") = a3;
	register long r7 __asm__("r7") = number;

	__asm__ volatile("svc 0"
			 : "+r"(r0)
			 : "r"(r1), "r"(r2), "r"(r3), "r"(r7)
			 : "memory", "cc", "ip");
	return r0;
}

static long syscall3(long number, long a0, long a1, long a2)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r2 __asm__("r2") = a2;
	register long r7 __asm__("r7") = number;

	__asm__ volatile("svc 0"
			 : "+r"(r0)
			 : "r"(r1), "r"(r2), "r"(r7)
			 : "memory", "cc", "ip");
	return r0;
}

void _start(void)
{
	static const char command[] = "bootloader";
	long ret = syscall4(88, 0xfee1dead, 0x28121969, 0x01234567,
			    (long)command);

	syscall3(1, ret ? 1 : 0, 0, 0);
	__builtin_unreachable();
}
