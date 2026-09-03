	.code32
	.section .text
	.globl resetAllConsonantFrication
	.globl filterAllDirectFrication
	.globl filterAllParallelFrication
	.type resetAllConsonantFrication,@function
	.type filterAllDirectFrication,@function
	.type filterAllParallelFrication,@function

	/* Called from Mode 19's inactive-frication branch. EAX addresses the
	 * established Mode-19 state and EDX is zero. The first three Mode-19 state
	 * words have already been cleared at the call site. */
.LblockStart:
resetAllConsonantFrication:
	movl %edx, 12(%eax)
	movl %edx, 16(%eax)
	pushl %edi
	leal (stateStart-resetAllConsonantFrication+0x2c)(%eax), %edi
	movl %edx, %eax
	/* Direct state plus one independent state pair for all six parallel
	 * formants. Keeping the states separate provides a hard branch boundary. */
	movl $14, %ecx
	rep stosl
	popl %edi
	ret

	/* Keep this entry at .xflt+0x320. It replaces the final multiply/pop tail
	 * of the existing direct-frication routine at .xflt+0. ST(0) contains that
	 * routine's sample; [ESP+4] is its saved EAX and [ESP+8] its caller return. */
	.balign 32
filterAllDirectFrication:
	/* Preserve the multiply that originally used [ESP+0x3c]. The extra CALL
	 * shifts that caller-owned gain to [ESP+0x40]. */
	fmuls 0x40(%esp)
	pushl %edx
	call .LdirectBase
.LdirectBase:
	popl %edx
	subl $8, %esp

	/* Direct-form-II-transposed biquad, using the dedicated direct state. */
	fstps 0(%esp)
	flds (tiltB0-.LdirectBase)(%edx)
	fmuls 0(%esp)
	fadds (directZ1-.LdirectBase)(%edx)
	fstps 4(%esp)

	flds (tiltB1-.LdirectBase)(%edx)
	fmuls 0(%esp)
	flds (tiltA1-.LdirectBase)(%edx)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fadds (directZ2-.LdirectBase)(%edx)
	fstps (directZ1-.LdirectBase)(%edx)

	flds (tiltB2-.LdirectBase)(%edx)
	fmuls 0(%esp)
	flds (tiltA2-.LdirectBase)(%edx)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fstps (directZ2-.LdirectBase)(%edx)

	flds 4(%esp)
	fmuls (directGain-.LdirectBase)(%edx)
	addl $8, %esp
	popl %edx
	/* Return directly to the engine caller: discard our return into the old
	 * tail, restore the EAX saved by .xflt+0, then use that caller's return. */
	addl $4, %esp
	popl %eax
	ret

	/* Keep this entry at .xflt+0x400. The engine calls it once for each
	 * completed parallel-formant buffer. All six stages use the same spectral
	 * pivot, including the dedicated s/t/z stages 5 and 6. */
	.balign 256
filterAllParallelFrication:
	pushal
	call .LparallelBase
.LparallelBase:
	popl %ebp
	movl %ebx, %eax
	subl $13, %eax
	cmpl $5, %eax
	ja .LparallelDone

	/* Give each of stages 1--6 its own two-word IIR state. */
	leal (parallelStates-.LparallelBase)(%ebp,%eax,8), %edi
	movl 0x13e3(%esi), %ebx
	movl 0x14f3(%esi), %ecx
	testl %ecx, %ecx
	jle .LparallelDone
	subl $8, %esp

.LparallelLoop:
	flds (%ebx)
	fstps 0(%esp)
	flds (tiltB0-.LparallelBase)(%ebp)
	fmuls 0(%esp)
	fadds 0(%edi)
	fstps 4(%esp)

	flds (tiltB1-.LparallelBase)(%ebp)
	fmuls 0(%esp)
	flds (tiltA1-.LparallelBase)(%ebp)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fadds 4(%edi)
	fstps 0(%edi)

	flds (tiltB2-.LparallelBase)(%ebp)
	fmuls 0(%esp)
	flds (tiltA2-.LparallelBase)(%ebp)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fstps 4(%edi)

	flds 4(%esp)
	fstps (%ebx)
	addl $4, %ebx
	decl %ecx
	jne .LparallelLoop
	addl $8, %esp

.LparallelDone:
	popal
	/* The block starts at .xflt+0x300, so the original mixer at .xflt+0x600
	 * is block-relative +0x300. Tail-jumping preserves its exact caller stack. */
	.byte 0xe9
	.long .LblockStart + 0x300 - . - 4

	/* The established +6/-10 dB spectral pivot. */
	.balign 4
tiltB0:
	.float 0.8451030710061816
tiltB1:
	.float 0.5499311376530391
tiltB2:
	.float 0.20911718551258923
tiltA1:
	.float -0.39536100764539944
tiltA2:
	.float 0.199341207209701

	/* Retain the established two-decibel reduction on the direct branch. */
directGain:
	.float 0.7943282347242815

	/* Contiguous state block cleared by resetAllConsonantFrication. */
stateStart:
directZ1:
	.float 0.0
directZ2:
	.float 0.0
parallelStates:
	.float 0.0, 0.0
	.float 0.0, 0.0
	.float 0.0, 0.0
	.float 0.0, 0.0
	.float 0.0, 0.0
	.float 0.0, 0.0
	.section .note.GNU-stack,"",@progbits
