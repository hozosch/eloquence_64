	.code32
	.section .text
	.globl nativeFricationHook
	.type nativeFricationHook,@function
nativeFricationHook:
	pushal
	call .Lbase
.Lbase:
	popl %eax
	addl $(filterState-.Lbase), %eax
	cmpl $0, 0x185b(%esi)
	jne .Lactive
	xorl %edx, %edx
	movl %edx, 0(%eax)
	movl %edx, 4(%eax)
	movl %edx, 8(%eax)
	movl %edx, 12(%eax)
	jmp .Ldone
.Lactive:
	movl 0x14f3(%esi), %ecx
	testl %ecx, %ecx
	jle .Ldone
	pushl $FILTER_MODE
	pushl %eax
	pushl %ecx
	leal 0x0d9b(%esi), %edx
	pushl %edx
	call processNativeFrication
	addl $16, %esp
.Ldone:
	popal
	/* The call return address shifts the original caller's stack by 4. */
	movl 0x10c(%esp), %edx
	ret

	.section .data
	.balign 4
filterState:
	.float 0.0, 0.0, 0.0, 0.0

	.section .note.GNU-stack,"",@progbits
