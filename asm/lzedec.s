; lzedec.s — LZE decoder for 6502 (ca65 syntax)
; Original Copyright (C)1995,2008 GORRY.
; Porting for 6502 by Kei Moroboshi 2020/Apr
; ca65 conversion for nes-image project
;
; Zero-page layout (placed after CC65 runtime vars at $00-$19):
;   $1A-$1B  LZEPtr    — pointer to compressed data (past 4-byte size header)
;   $1C-$1D  DECODEPtr — pointer to output buffer
;   $1E-$1F  DISTANCE  — back-reference source pointer (copy source)
;   $20      COPYCOUNT — copy length accumulator
;   $21      BITCOUNT  — bits remaining in current flag byte (held in A)
;
; Entry:
;   Set LZEPtr   ($1A/$1B) to the compressed data address (skip 4-byte header).
;   Set DECODEPtr($1C/$1D) to the output buffer address.
;   JSR DECODE_LZE
; Clobbers: A, X, Y, flags, ZP $1A-$21.

LZEZERO   = $1A
LZEPtr    = LZEZERO+0   ; $1A, $1B
DECODEPtr = LZEZERO+2   ; $1C, $1D
DISTANCE  = LZEZERO+4   ; $1E, $1F
COPYCOUNT = LZEZERO+6   ; $20
BITCOUNT  = LZEZERO+7   ; $21

.export DECODE_LZE
.export _lze_decode   ; C-callable alias: void lze_decode(void)

.segment "CODE"

_lze_decode:
    jmp DECODE_LZE

; ==============================================================================
; DECODE_LZE
; ==============================================================================

DECODE_LZE:
    LDY #0
    STY COPYCOUNT       ; CopyCount = 0
    LDX #1              ; BitCount = 1 (force flag-byte load on first BITTEST)

; BZCOMPATIBLE: first compressed byte is always a literal
LZESTORE:
    PHA                 ; save flag byte (A)
    JSR LZE_LDAPtrPP   ; A = *(LZEPtr++)
    STA (DECODEPtr),Y  ; *(DECODEPtr) = A
    INC DECODEPtr
    BNE LZESTASPE
    INC DECODEPtr+1
LZESTASPE:
    PLA                 ; restore flag byte

; ---- Main decode loop -------------------------------------------------------
LZEMAINLP:
    JSR LZEBITTEST
    BCS LZESTORE        ; bit=1: literal byte follows

; bit=0: back-reference; read one more bit
    JSR LZEBITTEST
    BCS LZECOPYWD       ; bit=01: word-distance match
                        ; bit=00: byte-distance match

; 00: Copy with Byte Distance (2-5 bytes, 1-byte negative offset)
LZECOPYBD:
    JSR LZEBITTEST
    ROL COPYCOUNT       ; accumulate 2 bits into COPYCOUNT

    JSR LZEBITTEST
    ROL COPYCOUNT

    PHA                                 ; save flag byte
    JSR LZE_LDAPtrPP                   ; A = distance byte D
    CLC
    ADC DECODEPtr                       ; DISTANCE_lo = DECODEPtr_lo + D
    STA DISTANCE
    LDA #$FF
    ADC DECODEPtr+1                     ; DISTANCE_hi = $FF + DECODEPtr_hi + carry
    STA DISTANCE+1                      ;             = DECODEPtr + D - 256

    STX BITCOUNT
    LDX COPYCOUNT
LZECPCNTP2:
    INX                                 ; count += 1
LZECPCNTP1:
    INX                                 ; count += 1 (total: COPYCOUNT + 2)

; ---- Inner copy loop --------------------------------------------------------
LZELDIR:
    LDA (DISTANCE),Y
    STA (DECODEPtr),Y
    INY
    BEQ LZEINCH         ; Y wrapped: page-cross handling
    DEX
    BNE LZELDIR

; ---- Normalise DECODEPtr after copy -----------------------------------------
LZENORM:
    TYA                 ; DECODEPtr += Y
    CLC
    ADC DECODEPtr
    STA DECODEPtr
    BCC LZENOINC
    INC DECODEPtr+1
LZENOINC:
    LDY #0
    STY COPYCOUNT
    LDX BITCOUNT
    PLA                 ; restore flag byte
    JMP LZEMAINLP

; ---- Page-cross during inner copy -------------------------------------------
LZEINCH:
    INC DISTANCE+1
    INC DECODEPtr+1
    DEX
    BNE LZELDIR
    BEQ LZENORM

; 01: Copy with Word Distance (2+ bytes, 13-bit offset)
LZECOPYWD:
    PHA                                 ; save flag byte
    JSR LZE_LDAPtrPP
    STA DISTANCE+1                      ; high byte (packed: distance hi + count lo)
    JSR LZE_LDAPtrPP
    STA COPYCOUNT                       ; low byte (packed: distance lo + count bits)

    LSR DISTANCE+1                      ; unpack: shift 16-bit value right 3
    ROR A
    LSR DISTANCE+1
    ROR A
    LSR DISTANCE+1
    ROR A
    CLC
    ADC DECODEPtr
    STA DISTANCE
    LDA DISTANCE+1
    ORA #$E0                            ; sign-extend: set top 3 bits for neg offset
    ADC DECODEPtr+1
    STA DISTANCE+1

    STX BITCOUNT
    LDA COPYCOUNT
    AND #7
    TAX
    BNE LZECPCNTP2

    JSR LZE_LDAPtrPP                   ; explicit copy count byte
    TAX
    BNE LZECPCNTP1

; End-of-data marker (three zero bytes produced by the encoder)
LZEDECODE_END:
    PLA
    RTS

; ==============================================================================
; LZE_LDAPtrPP — load byte at (LZEPtr),Y and post-increment LZEPtr
; ==============================================================================
LZE_LDAPtrPP:
    LDA (LZEPtr),Y
    INC LZEPtr
    BNE LZELDASPE
    INC LZEPtr+1
LZELDASPE:
    RTS

; ==============================================================================
; LZEBITTEST — shift A left 1; reload flag byte from stream when exhausted
;              On return: C = next bit value (1 = literal, 0 = back-ref)
; ==============================================================================
LZEBITTEST:
    DEX
    BNE LZESKIP         ; still bits left in A
    JSR LZE_LDAPtrPP   ; A = new flag byte
    LDX #8              ; 8 bits available
LZESKIP:
    ASL A               ; shift MSB into carry
    RTS
