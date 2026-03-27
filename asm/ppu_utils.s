; ppu_utils.s — PPU utility functions
;
; void ppu_chr_copy(void)
;   Copy 4096 bytes from WRAM $6000-$6FFF to PPU CHR-RAM $0000-$0FFF.
;   PPU rendering must be disabled (PPU_MASK = $00) before calling.
;   Uses ZP $22-$23 as a temporary source pointer (overwritten).

.export _ppu_chr_copy

.segment "CODE"

_ppu_chr_copy:
    bit $2002           ; reset PPU address toggle
    lda #$00
    sta $2006           ; PPU VRAM address hi = $00
    sta $2006           ; PPU VRAM address lo = $00  → dest $0000

    sta $22             ; source ptr lo = $00
    lda #$60
    sta $23             ; source ptr hi = $60  → WRAM base $6000

    ldx #16             ; 16 pages × 256 bytes = 4096 bytes
@page:
    ldy #0
@byte:
    lda ($22),y
    sta $2007           ; auto-increments PPU address
    iny
    bne @byte
    inc $23             ; next 256-byte page
    dex
    bne @page
    rts
