	.code32
	.section .text
	.globl resetSplitFrication
	.globl filterDirectFrication
	.globl filterParallelFrication
	.type resetSplitFrication,@function
	.type filterDirectFrication,@function
	.type filterParallelFrication,@function

	/* Called from Mode 19's inactive-frication branch. EAX addresses the
	 * established Mode-19 state and EDX is zero. The first three Mode-19 state
	 * words have already been cleared at the call site. */
.LblockStart:
resetSplitFrication:
	movl %edx, 12(%eax)
	movl %edx, 16(%eax)
	pushl %edi
	leal (stateStart-resetSplitFrication+0x2c)(%eax), %edi
	movl %edx, %eax
	/* Direct state, four parallel states, and one shared native hold. */
	movl $11, %ecx
	rep stosl
	popl %edi
	ret

	/* Keep this entry at .xflt+0x320. It replaces the final multiply/pop tail
	 * of the existing direct-frication routine at .xflt+0. ST(0) contains that
	 * routine's sample; [ESP+4] is its saved EAX and [ESP+8] its caller return. */
	.balign 32
filterDirectFrication:
	/* Preserve the multiply that originally used [ESP+0x3c]. The extra CALL
	 * shifts that caller-owned gain to [ESP+0x40]. */
	fmuls 0x40(%esp)
	pushl %edx
	call .LdirectBase
.LdirectBase:
	popl %edx

	/* This is a categorical split, not a gain fade. Dedicated s/t/z activity
	 * refreshes a short native hold so a stage-level hole cannot expose the
	 * filtered path inside that consonant. Unlike the former event-long latch,
	 * the hold expires after 48 direct samples (3 ms at 16 kHz), allowing an
	 * immediately following f/ch/p/b consonant to enter the filtered path. */
	movl 0x5ee(%esi), %eax
	andl $0x7fffffff, %eax
	jne .LrefreshDirectST
	movl 0x63e(%esi), %eax
	andl $0x7fffffff, %eax
	jne .LrefreshDirectST
	movl (nativeHold-.LdirectBase)(%edx), %eax
	testl %eax, %eax
	jz .LfilterDirect
	decl %eax
	movl %eax, (nativeHold-.LdirectBase)(%edx)
	jmp .LbypassDirectST

.LrefreshDirectST:
	movl $48, (nativeHold-.LdirectBase)(%edx)
	jmp .LbypassDirectST

.LfilterDirect:
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
	jmp .LdirectReturn

.LbypassDirectST:
	/* Preserve ST(0), but discard the previous filtered consonant's tail. */
	xorl %eax, %eax
	movl %eax, (directZ1-.LdirectBase)(%edx)
	movl %eax, (directZ2-.LdirectBase)(%edx)

.LdirectReturn:
	popl %edx
	/* Return directly to the engine caller: discard our return into the old
	 * tail, restore the EAX saved by .xflt+0, then use that caller's return. */
	addl $4, %esp
	popl %eax
	ret

	/* Keep this entry at .xflt+0x400. The engine calls it once for each
	 * completed parallel-formant buffer. Stages 1--4 (EBX 13--16) carry the
	 * ch/sch resonances; stages 5--6 (EBX 17--18) carry s/t and tail-jump to the
	 * original mixer untouched. */
	.balign 256
filterParallelFrication:
	pushal
	call .LparallelBase
.LparallelBase:
	popl %ebp
	movl %ebx, %eax
	subl $13, %eax
	cmpl $3, %eax
	ja .LparallelDone

	/* Give each of stages 1--4 its own two-word IIR state. */
	leal (parallelStates-.LparallelBase)(%ebp,%eax,8), %edi

	/* Share the bounded native hold with the sample-rate direct branch. */
	movl 0x5ee(%esi), %edx
	andl $0x7fffffff, %edx
	jne .LrefreshParallelST
	movl 0x63e(%esi), %edx
	andl $0x7fffffff, %edx
	jne .LrefreshParallelST
	cmpl $0, (nativeHold-.LparallelBase)(%ebp)
	jne .LbypassNativeST
	jmp .LfilterParallel

.LrefreshParallelST:
	movl $48, (nativeHold-.LparallelBase)(%ebp)
	jmp .LbypassNativeST

.LfilterParallel:
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
	jmp .LparallelDone

.LbypassNativeST:
	/* Do not carry stale ch/sch filter state into a native s/t interval. */
	xorl %edx, %edx
	movl %edx, 0(%edi)
	movl %edx, 4(%edi)

.LparallelDone:
	popal
	/* The block starts at .xflt+0x300, so the original mixer at .xflt+0x600
	 * is block-relative +0x300. Tail-jumping preserves its exact caller stack. */
	.byte 0xe9
	.long .LblockStart + 0x300 - . - 4

	/* The +6/-10 dB spectral pivot used by the successful preceding build. */
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

	/* The direct f/w/b/p branch is another 2 dB quieter than the parallel
	 * ch/sch branches. */
directGain:
	.float 0.7943282347242815

	/* Contiguous state block cleared by resetSplitFrication. */
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
nativeHold:
	.long 0

	.section .note.GNU-stack,"",@progbits
