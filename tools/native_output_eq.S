	.code32
	.section .text
	.globl resetNativeOutputEq
	.globl processNativeOutput
	.type resetNativeOutputEq,@function
	.type processNativeOutput,@function

resetNativeOutputEq:
	/* This entry remains part of the stable injected-data ABI. The release patch
	 * deliberately does not call it during consonant-state resets. */
	pushal
	call .LresetBase
.LresetBase:
	popl %ebp
	leal (stateStart-.LresetBase)(%ebp), %edi
	xorl %eax, %eax
	movl $6, %ecx
	rep stosl
	popal
	ret

	.balign 32
processNativeOutput:
	pushal
	call .LprocessBase
.LprocessBase:
	popl %ebp

	movl 0x14f3(%esi), %ecx
	testl %ecx, %ecx
	jle .Ldone
	movl 0x0d93(%esi), %edi
	subl $8, %esp

.LsampleLoop:
	flds (%edi)
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

	/* Keep the injected data ABI stable for the patch generator. */
	.space 0x100 - (. - resetNativeOutputEq), 0x90
	.balign 4
filterStageCount:
	.long 2
	/* Reserved words preserve the native output-EQ data ABI. */
	.float 1.0, 1.0, 1.0, 0.04

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
