	.code32
	.section .text
	.globl loadShiftedSibilanceFrequency
	.type loadShiftedSibilanceFrequency,@function

	/* Replaces `flds 0xa0(%esp,%ebx)` in the native resonator-coefficient
	 * setup loop. The CALL return address shifts the original frame by four
	 * bytes. EBX is a byte offset: 0x10 and 0x14 select parallel F5 and F6. */
loadShiftedSibilanceFrequency:
	cmpl $0x10, %ebx
	je .Lcandidate
	cmpl $0x14, %ebx
	jne .Loriginal

.Lcandidate:
	/* The unsmoothed target amplitude for the matching resonator is at E0h in
	 * the original frame. A zero target leaves vowels and inactive tails at the
	 * exact v21 frequency; the engine performs its own coefficient smoothing. */
	cmpl $0, 0xe4(%esp,%ebx)
	je .Loriginal
	flds 0xa4(%esp,%ebx)

	/* The patch generator replaces this 1.0f immediate with the requested
	 * semitone ratio. Using the stack preserves every general-purpose register. */
	pushl $0x3f800000
	fmuls (%esp)
	addl $4, %esp
	ret

.Loriginal:
	flds 0xa4(%esp,%ebx)
	ret
	.section .note.GNU-stack,"",@progbits
