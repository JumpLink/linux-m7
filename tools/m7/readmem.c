/* Read the fixed M7 Pstore region without libc. */
static unsigned char buffer[1024 * 1024];

static long syscall3(long number, long a0, long a1, long a2)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r2 __asm__("r2") = a2;
	register long r7 __asm__("r7") = number;
	/* The recovery kernel clobbers r12 and the condition flags. */
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory", "cc", "ip");
	return r0;
}

static long syscall5(long number, long a0, long a1, long a2, long a3, long a4)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r2 __asm__("r2") = a2;
	register long r3 __asm__("r3") = a3;
	register long r4 __asm__("r4") = a4;
	register long r7 __asm__("r7") = number;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r7) : "memory", "cc", "ip");
	return r0;
}

static __attribute__((noreturn)) void exit_process(long status)
{
	syscall3(1, status, 0, 0);
	__builtin_unreachable();
}

void _start(void)
{
	static const char path[] = "/dev/mem";
	long fd = syscall3(5, (long)path, 0, 0);
	if (fd < 0)
		exit_process(1);

	/* ARM _llseek splits the offset and takes SEEK_SET as its fifth argument. */
	long result = 0;
	long offset = syscall5(140, fd, 0, 0x86000000, (long)&result, 0);
	if (offset < 0)
		exit_process(2);

	long done = 0;
	while (done < (long)sizeof(buffer)) {
		long count = syscall3(3, fd, (long)(buffer + done), sizeof(buffer) - done);
		if (count <= 0)
			exit_process(3);
		done += count;
	}
	while (done > 0) {
		long count = syscall3(4, 1, (long)(buffer + sizeof(buffer) - done), done);
		if (count <= 0)
			exit_process(4);
		done -= count;
	}
	exit_process(0);
}
