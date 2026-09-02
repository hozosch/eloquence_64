SECTIONS
{
	. = 0;
	.text : { *(.text*) }
	.rodata : { *(.rodata*) }
	.got : { *(.got*) }
	.data : { *(.data*) }
	/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
