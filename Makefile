# Makefile - NES slideshow (CC65 toolchain)
# Install CC65: sudo apt install cc65

TARGET  = image.nes

CC65    = cc65
CA65    = ca65
LD65    = ld65

CFLAGS  = -t nes -O
ASFLAGS = -t nes

OBJS = build/zeropage.o build/crt0.o build/main.o \
       build/lzedec.o build/ppu_utils.o build/img_data.o

# -------------------------------------------------------
.PHONY: all clean

all: $(TARGET)

NESLIB = /usr/share/cc65/lib/nes.lib

$(TARGET): $(OBJS) nes.cfg
	$(LD65) -C nes.cfg -o $@ $(OBJS) $(NESLIB)
	@echo "Built $(TARGET) (size: $$(wc -c < $(TARGET)) bytes)"

build/main.o: src/main.c asm/img_data.s | build
	$(CC65) $(CFLAGS) -o build/main.s $<
	$(CA65) $(ASFLAGS) -o $@ build/main.s

build/zeropage.o: asm/zeropage.s | build
	$(CA65) $(ASFLAGS) -o $@ $<

build/crt0.o: asm/crt0.s | build
	$(CA65) $(ASFLAGS) -o $@ $<

build/lzedec.o: asm/lzedec.s | build
	$(CA65) $(ASFLAGS) -o $@ $<

build/ppu_utils.o: asm/ppu_utils.s | build
	$(CA65) $(ASFLAGS) -o $@ $<

# GREEN_RESCUE=0 to disable:  make GREEN_RESCUE=0
GREEN_RESCUE ?= 1
ifeq ($(GREEN_RESCUE),0)
MAKE_CHR_FLAGS += --no-green-rescue
endif

# SRC_DIR: source image directory  make SRC_DIR=../src2
ifdef SRC_DIR
MAKE_CHR_FLAGS += --src-dir $(SRC_DIR)
endif

# MAX_IMAGES: limit number of images  make MAX_IMAGES=10
ifdef MAX_IMAGES
MAKE_CHR_FLAGS += --max-images $(MAX_IMAGES)
endif

asm/img_data.s: tools/make_chr.py
	python3 tools/make_chr.py $(MAKE_CHR_FLAGS)

build/img_data.o: asm/img_data.s | build
	$(CA65) $(ASFLAGS) -o $@ $<

build:
	mkdir -p build

clean:
	rm -rf build $(TARGET) asm/img_data.s
