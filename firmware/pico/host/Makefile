# Host build of the pure-logic firmware parts (no Pico SDK needed).
CFLAGS ?= -O2 -Wall -Wextra -Werror -std=c11
SRC := ../src
OUT := build

all: $(OUT)/test_timing $(OUT)/schedule_cli

$(OUT):
	mkdir -p $(OUT)

$(OUT)/test_timing: test_timing.c $(SRC)/lm_timing.c $(SRC)/lm_timing.h | $(OUT)
	$(CC) $(CFLAGS) -I$(SRC) test_timing.c $(SRC)/lm_timing.c -lm -o $@

$(OUT)/schedule_cli: schedule_cli.c $(SRC)/lm_timing.c $(SRC)/lm_timing.h | $(OUT)
	$(CC) $(CFLAGS) -I$(SRC) schedule_cli.c $(SRC)/lm_timing.c -lm -o $@

test: $(OUT)/test_timing
	./$(OUT)/test_timing

clean:
	rm -rf $(OUT)

.PHONY: all test clean
