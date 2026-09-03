	.code32
	.section .text
	.globl resetNativeOutputEq
	.globl processNativeOutput
	.type resetNativeOutputEq,@function
	.type processNativeOutput,@function

resetNativeOutputEq:
	pushal
	call .LresetBase
.LresetBase:
	popl %ebp
	leal (stateStart-.LresetBase)(%ebp), %edi
	xorl %eax, %eax
	movl $6, %ecx
	rep stosl
	fld1
	fstps (smoothedVoicedGain-.LresetBase)(%ebp)
	popal
	ret

	.balign 32
processNativeOutput:
	pushal
	call .LprocessBase
.LprocessBase:
	popl %ebp

	/* The complete voiced signal approaches -1.5 dB. Exact s/t/z targets and
	 * unvoiced frames approach unity so native s remains untouched. */
	leal (unityGain-.LprocessBase)(%ebp), %edx
	cmpl $0, 0x1853(%esi)
	je .LtargetReady
	cmpl $0, 0x114(%esp)
	jne .LtargetReady
	cmpl $0, 0x118(%esp)
	jne .LtargetReady
	leal (voicedGain-.LprocessBase)(%ebp), %edx

.LtargetReady:
	movl 0x14f3(%esi), %ecx
	testl %ecx, %ecx
	jle .Ldone
	movl 0x0d93(%esi), %edi
	subl $8, %esp

.LsampleLoop:
	/* Persistent one-pole gain envelope: g += alpha * (target - g). */
	flds (%edx)
	fsubs (smoothedVoicedGain-.LprocessBase)(%ebp)
	fmuls (voicedGainSmoothing-.LprocessBase)(%ebp)
	fadds (smoothedVoicedGain-.LprocessBase)(%ebp)
	fstps (smoothedVoicedGain-.LprocessBase)(%ebp)
	flds (%edi)
	fmuls (smoothedVoicedGain-.LprocessBase)(%ebp)
	fstps 0(%esp)

	/* Run the low shelf and v21 shelf. The presence-enabled native patch raises
	 * the stage count to three and supplies the 4 kHz peaking coefficients. */
	leal (stageCoefficients-.LprocessBase)(%ebp), %eax
	leal (stateStart-.LprocessBase)(%ebp), %ebx
	movl (filterStageCount-.LprocessBase)(%ebp), %esi

.LstageLoop:
	flds 0(%eax)
	fmuls 0(%esp)
	fadds 0(%ebx)
	fstps 4(%esp)

	flds 4(%eax)
	fmuls 0(%esp)
	flds 12(%eax)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fadds 4(%ebx)
	fstps 0(%ebx)

	flds 8(%eax)
	fmuls 0(%esp)
	flds 16(%eax)
	fmuls 4(%esp)
	fchs
	faddp %st, %st(1)
	fstps 4(%ebx)

	flds 4(%esp)
	fstps 0(%esp)
	addl $20, %eax
	addl $8, %ebx
	decl %esi
	jne .LstageLoop

	flds 0(%esp)
	fstps (%edi)
	addl $4, %edi
	decl %ecx
	jne .LsampleLoop
	addl $8, %esp

.Ldone:
	popal
	/* Reproduce the final-buffer count load replaced by the outer hook. */
	movl 0x14f3(%esi), %eax
	ret

	.balign 4
filterStageCount:
	.long 2
unityGain:
	.float 1.0
voicedGain:
	.float 1.0
smoothedVoicedGain:
	.float 1.0
voicedGainSmoothing:
	.float 0.04

	/* Three identity placeholders replaced by the patch generator. */
stageCoefficients:
	.float 1.0, 0.0, 0.0, 0.0, 0.0
	.float 1.0, 0.0, 0.0, 0.0, 0.0
	.float 1.0, 0.0, 0.0, 0.0, 0.0

stateStart:
	.float 0.0, 0.0
	.float 0.0, 0.0
	.float 0.0, 0.0

	.section .note.GNU-stack,"",@progbits
