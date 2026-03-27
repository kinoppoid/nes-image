; zeropage.s - CC65 zero page variables required by all cc65-compiled code
;
; cc65 always imports these symbols via:
;   .importzp sp, sreg, regsave, regbank
;   .importzp tmp1, tmp2, tmp3, tmp4, ptr1, ptr2, ptr3, ptr4
;
; We define and export them here instead of linking nes.lib.

.exportzp sp, sreg, regsave, regbank
.exportzp tmp1, tmp2, tmp3, tmp4, ptr1, ptr2, ptr3, ptr4

.segment "ZEROPAGE"

sp:       .res 2   ; CC65 software stack pointer (16-bit)
sreg:     .res 2   ; Secondary register (used for 32-bit ops)
regsave:  .res 4   ; Register save area
regbank:  .res 6   ; Register bank (register variables)
tmp1:     .res 1   ; Scratch temporaries
tmp2:     .res 1
tmp3:     .res 1
tmp4:     .res 1
ptr1:     .res 2   ; Pointer temporaries
ptr2:     .res 2
ptr3:     .res 2
ptr4:     .res 2
