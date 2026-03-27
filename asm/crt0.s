; crt0.s - NES startup code, iNES header, interrupt vectors

; ============================================================
; iNES header (16 bytes)
; ============================================================
.segment "HEADER"
    .byte $4E,$45,$53,$1A   ; "NES" + EOF marker
    .byte 2                  ; 2 x 16KB PRG-ROM banks (32KB total)
    .byte 0                  ; 0 CHR-ROM banks = CHR-RAM (tile data written at runtime)
    .byte $02                ; Mapper 0, horizontal mirroring, SRAM/WRAM enabled ($6000-$7FFF)
    .byte $00                ; No special flags
    .byte $00,$00,$00,$00,$00,$00,$00,$00  ; Padding

; ============================================================
; Reset handler (entry point at $8000)
; ============================================================
.import  _main
.importzp sp              ; CC65 software stack pointer (defined in zeropage.s)

; Required by cc65: signals that startup code is present
.export  __STARTUP__ : absolute = 1

.segment "STARTUP"

reset:
    sei               ; Disable IRQ
    cld               ; Clear decimal mode
    ldx #$40
    stx $4017         ; Disable APU frame counter IRQ
    ldx #$FF
    txs               ; Initialize stack pointer
    inx               ; X = 0
    stx $2000         ; Disable NMI
    stx $2001         ; Disable PPU rendering
    stx $4010         ; Disable DMC IRQ

    ; Wait for first PPU vblank
@vblank1:
    bit $2002
    bpl @vblank1

    ; Clear all CPU RAM ($0000-$07FF)
    txa               ; A = 0
@clrram:
    sta $000,X
    sta $100,X
    sta $200,X
    sta $300,X
    sta $400,X
    sta $500,X
    sta $600,X
    sta $700,X
    inx
    bne @clrram

    ; Wait for second PPU vblank (PPU fully ready)
@vblank2:
    bit $2002
    bpl @vblank2

    ; Initialize CC65 software stack pointer to top of RAM ($0800)
    ; (grows downward into $0700-$07FF)
    lda #$00
    sta sp
    lda #$08
    sta sp+1

    ; Jump to C main() — main() loads image 0 and handles all PPU setup
    jsr _main

@forever:
    jmp @forever

; ============================================================
; Interrupt handlers
; ============================================================
nmi:
    rti

irq:
    rti

; ============================================================
; Interrupt vectors ($FFFA-$FFFF)
; ============================================================
.segment "VECTORS"
    .word nmi         ; $FFFA: NMI vector
    .word reset       ; $FFFC: Reset vector
    .word irq         ; $FFFE: IRQ/BRK vector
