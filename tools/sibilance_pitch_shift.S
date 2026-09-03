	.code32
	.section .text
	.globl loadShiftedSibilanceFrequency
	.type loadShiftedSibilanceFrequency,@function

	/* Replaces `flds 0xa0(%esp,%ebx)` in the native resonator-coefficient
	 * setup loop. The CALL return address shifts the original frame by four
	 * bytes. EBX is a byte offset: 0x08 through 0x14 select parallel F3--F6. */
loadShiftedSibilanceFrequency:
	cmpl $0x08, %ebx
	jb .Loriginal
	cmpl $0x14, %ebx
	ja .Loriginal

	/* The outer frame's exact F5/F6 target flags are at F0h/F4h. They move to
	 * F4h/F8h here because of the CALL return address. If either is active, this
	 * is the native s/t/z resonator block: shift F3--F6 together rather than
	 * moving only two weak upper resonances. Vowels and inactive tails keep the
	 * exact v21 frequencies. */
	cmpl $0, 0xf4(%esp)
	jne .Lshift
	cmpl $0, 0xf8(%esp)
	je .Loriginal

.Lshift:
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
