	.code32
	.section .text
	.globl resetSplitFrication
	.globl filterDirectFrication
	.globl filterParallelFrication
	.type resetSplitFrication,@function
	.type filterDirectFrication,@function
	.type filterParallelFrication,@function

	/* This is the comparison variant of split_frication_paths.S. In addition
	 * to its hard direct/ch/sch routing, it gives the shared s/t/z stages their
	 * own spectral-pivot filter and completely separate state. */
.LblockStart:
resetSplitFrication:
	movl %edx, 12(%eax)
	movl %edx, 16(%eax)
	pushl %edi
	leal (stateStart-resetSplitFrication+0x2c)(%eax), %edi
	movl %edx, %eax
	/* Direct state, four ch/sch states and two s/t/z states. */
	movl $14, %ecx
	rep stosl
	popl %edi
	ret

	/* Keep this entry at .xflt+0x320. */
	.balign 32
filterDirectFrication:
	fmuls 0x40(%esp)
	pushl %edx
	call .LdirectBase
.LdirectBase:
	popl %edx

	/* F5/F6 target flags provide the hard boundary around the native s/t/z
	 * path. The direct path is filtered only while both are inactive. */
	cmpl $0, 0x100(%esp)
	jne .LbypassDirectST
	cmpl $0, 0x104(%esp)
	jne .LbypassDirectST

	subl $8, %esp
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
	xorl %eax, %eax
	movl %eax, (directZ1-.LdirectBase)(%edx)
	movl %eax, (directZ2-.LdirectBase)(%edx)

.LdirectReturn:
	popl %edx
	addl $4, %esp
	popl %eax
	ret

	/* Keep this entry at .xflt+0x400. EBX 13--16 are the ch/sch stages and
	 * EBX 17--18 are the shared s/t/z stages. Exact target flags select one
	 * side; the other side's state is zeroed immediately. */
	.balign 256
filterParallelFrication:
	pushal
	call .LparallelBase
.LparallelBase:
	popl %ebp
	movl %ebx, %eax
	subl $13, %eax
	cmpl $5, %eax
	ja .LparallelDone

	movl 12(%esp), %edx
	cmpl $0, 0xf4(%edx)
	jne .LnativeSTActive
	cmpl $0, 0xf8(%edx)
	jne .LnativeSTActive

	/* No current s/t/z target: process ch/sch stages 1--4 and clear any
	 * previous s/t/z state when their two stages arrive. */
	cmpl $3, %eax
	ja .LclearInactiveST
	leal (parallelStates-.LparallelBase)(%ebp,%eax,8), %edi
	leal (tiltB0-.LparallelBase)(%ebp), %edx
	xorl %eax, %eax
	jmp .LfilterParallel

.LclearInactiveST:
	subl $4, %eax
	leal (sibilanceStates-.LparallelBase)(%ebp,%eax,8), %edi
	jmp .LclearParallelState

.LnativeSTActive:
	/* During s/t/z, clear ch/sch states but process stages 5--6 through their
	 * dedicated roll-off. No history crosses the hard consonant boundary. */
	cmpl $3, %eax
	jbe .LclearBypassedCH
	subl $4, %eax
	leal (sibilanceStates-.LparallelBase)(%ebp,%eax,8), %edi

	/* A unity placeholder keeps the established baseline bit-identical. For a
	 * comparison boost, the outer frame's current AV value at +4 distinguishes
	 * voiced z/s from unvoiced s/t without carrying detector state across the
	 * hard consonant boundary. */
	xorl %eax, %eax
	cmpl $0x3f800000, (voicedSBoost-.LparallelBase)(%ebp)
	je .LsibilanceCoefficients
	movl 0x10c(%edx), %ecx
	cmpl $0, 4(%ecx)
	setne %al
.LsibilanceCoefficients:
	leal (sibilanceB0-.LparallelBase)(%ebp), %edx
	jmp .LfilterParallel

.LclearBypassedCH:
	leal (parallelStates-.LparallelBase)(%ebp,%eax,8), %edi

.LclearParallelState:
	xorl %ecx, %ecx
	movl %ecx, 0(%edi)
	movl %ecx, 4(%edi)
	jmp .LparallelDone

.LfilterParallel:
	movl 0x13e3(%esi), %ebx
	movl 0x14f3(%esi), %ecx
	testl %ecx, %ecx
	jle .LparallelDone
	subl $8, %esp

.LparallelLoop:
	flds (%ebx)
	fstps 0(%esp)
	flds 0(%edx)
	fmuls 0(%esp)
	fadds 0(%edi)
	fstps 4(%esp)

	flds 4(%edx)
	fmuls 0(%esp)
	flds 12(%edx)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fadds 4(%edi)
	fstps 0(%edi)

	flds 8(%edx)
	fmuls 0(%esp)
	flds 16(%edx)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fstps 4(%edi)

	flds 4(%esp)
	testl %eax, %eax
	je .LstoreParallel
	fmuls (voicedSBoost-.LparallelBase)(%ebp)
.LstoreParallel:
	fstps (%ebx)
	addl $4, %ebx
	decl %ecx
	jne .LparallelLoop
	addl $8, %esp

.LparallelDone:
	popal
	.byte 0xe9
	.long .LblockStart + 0x300 - . - 4

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

	/* Identity placeholder replaced by the patch generator. */
sibilanceB0:
	.float 1.0
sibilanceB1:
	.float 0.0
sibilanceB2:
	.float 0.0
sibilanceA1:
	.float 0.0
sibilanceA2:
	.float 0.0

voicedSBoost:
	.float 1.0
voicedGain:
	.float 1.0

directGain:
	.float 0.7943282347242815

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
sibilanceStates:
	.float 0.0, 0.0
	.float 0.0, 0.0

	/* Called from the native-frication wrapper before its original return. At
	 * this point the cascade/voiced buffer exists at d93, while direct frication
	 * and the parallel consonant buffers have not been added yet. Scaling here
	 * therefore leaves all unvoiced consonant paths untouched. */
	.balign 16
	.globl scaleVoicedBuffer
	.type scaleVoicedBuffer,@function
scaleVoicedBuffer:
	pushal
	call .LvoicedBase
.LvoicedBase:
	popl %ebp

	/* The nested CALL and PUSHAL put the outer frame pointer at ESP+130h. AV is
	 * the float at frame+4; an exact zero means the current frame is unvoiced. */
	movl 0x130(%esp), %edx
	cmpl $0, 4(%edx)
	je .LvoicedDone
	movl 0x14f3(%esi), %ecx
	testl %ecx, %ecx
	jle .LvoicedDone
	leal 0x0d93(%esi), %edi
.LvoicedLoop:
	flds (%edi)
	fmuls (voicedGain-.LvoicedBase)(%ebp)
	fstps (%edi)
	addl $4, %edi
	decl %ecx
	jne .LvoicedLoop

.LvoicedDone:
	popal
	/* Reproduce the instruction replaced by the outer frication hook. */
	movl 0x110(%esp), %edx
	ret
	.section .note.GNU-stack,"",@progbits
