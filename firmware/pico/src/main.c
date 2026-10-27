// Pico timing controller: club gates -> camera exposure + IR strobe burst.
//
// The Raspberry Pi can't time microsecond events, so this board does it:
//   1. two optical gates behind the ball fire as the club passes
//   2. lm_compute_schedule() predicts impact and lays out the flashes
//   3. a busy-wait loop (interrupts off) drives the camera trigger lines and
//      LED driver exactly on schedule
//   4. the actual schedule is printed as one JSON line over USB serial for the Pi
//
// Serial commands (newline-terminated): PING, TEST <club_mps>, FLASH
// UNTESTED ON HARDWARE: pin polarity and camera trigger behaviour need bench
// verification (see docs/wiring.md, "Camera trigger").
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/gpio.h"
#include "hardware/sync.h"
#include "lm_timing.h"
#include "pico/stdlib.h"

// Pin map (see docs/wiring.md)
#define PIN_GATE1 2      // comparator output, rising edge = club present
#define PIN_GATE2 3
#define PIN_STROBE 15    // LED driver input, high = LEDs on
#define PIN_CAM_FIRST 16 // GP16..GP19 -> ULN2003A -> camera J3 TRIG- (4-camera ready)
#define N_CAM_PINS 4
// InnoMaker CAM-IMX296Mono-GS: the J3 opto LED is lit while idle and the sensor triggers
// on its falling edge (LED off). Through the inverting ULN2003A, pin high = LED on, so
// the pin is LOW while exposing. Whether the low-pulse width sets the exposure time (it
// does in the IMX296's pulse-width trigger mode) is UNVERIFIED on the bench; if not, set
// the exposure in libcamera to cover the whole burst.
#define CAM_TRIG_ACTIVE_LOW 1

#define GATE_TIMEOUT_US 60000   // gate 2 must follow gate 1 within this
#define LOCKOUT_US 1500000      // between shots: debounce + LED thermal limit
#define MAX_PULSE_US 40         // hard cap; protects the overdriven LEDs

static volatile uint64_t t_gate1, t_gate2;
static volatile bool got_gate1, got_gate2;
static uint64_t lockout_until;
static lm_timing_cfg_t cfg;

static void gate_irq(uint gpio, uint32_t events) {
    (void)events;
    uint64_t now = time_us_64();
    if (now < lockout_until) return;
    if (gpio == PIN_GATE1 && !got_gate1) {
        t_gate1 = now;
        got_gate1 = true;
    } else if (gpio == PIN_GATE2 && got_gate1 && !got_gate2) {
        t_gate2 = now;
        got_gate2 = true;
    }
}

static void cams_set(bool exposing) {
    bool level = CAM_TRIG_ACTIVE_LOW ? !exposing : exposing;
    for (int i = 0; i < N_CAM_PINS; i++) gpio_put(PIN_CAM_FIRST + i, level);
}

static void run_schedule(const lm_schedule_t *s) {
    int64_t pulse = cfg.pulse_us > MAX_PULSE_US ? MAX_PULSE_US : cfg.pulse_us;
    uint32_t irq = save_and_disable_interrupts();
    busy_wait_until(from_us_since_boot((uint64_t)s->exposure_start_us));
    cams_set(true);
    for (int i = 0; i < s->n_flashes; i++) {
        busy_wait_until(from_us_since_boot((uint64_t)s->flash_us[i]));
        gpio_put(PIN_STROBE, 1);
        busy_wait_until(from_us_since_boot((uint64_t)(s->flash_us[i] + pulse)));
        gpio_put(PIN_STROBE, 0);
    }
    busy_wait_until(from_us_since_boot((uint64_t)s->exposure_end_us));
    cams_set(false);
    restore_interrupts(irq);
}

static void report(const lm_schedule_t *s) {
    if (!s->ok) {
        printf("{\"type\":\"error\",\"msg\":\"%s\",\"club_speed\":%.2f}\n", s->error, s->club_speed);
        return;
    }
    printf("{\"type\":\"shot\",\"club_speed\":%.3f,\"t_impact\":%lld,\"flashes\":[", s->club_speed,
           (long long)s->t_impact_us);
    for (int i = 0; i < s->n_flashes; i++)
        printf("%s[%lld,%d]", i ? "," : "", (long long)(s->flash_us[i] - s->t_impact_us), s->flash_kind[i]);
    printf("],\"exposure\":[%lld,%lld]}\n", (long long)(s->exposure_start_us - s->t_impact_us),
           (long long)(s->exposure_end_us - s->t_impact_us));
}

static void fire(uint64_t t1, uint64_t t2) {
    lm_schedule_t s;
    lm_compute_schedule(&cfg, (int64_t)t1, (int64_t)t2, &s);
    if (s.ok) run_schedule(&s);
    report(&s);
    lockout_until = time_us_64() + LOCKOUT_US;
}

static void handle_command(char *line) {
    if (strcmp(line, "PING") == 0) {
        printf("{\"type\":\"pong\"}\n");
    } else if (strncmp(line, "TEST ", 5) == 0) {
        // Simulated gates starting now, for bench tests with a hand-dropped ball.
        double v = atof(line + 5);
        if (v <= 0) return;
        uint64_t t1 = time_us_64();
        fire(t1, t1 + (uint64_t)((cfg.gate1_m - cfg.gate2_m) / v * 1e6));
    } else if (strcmp(line, "FLASH") == 0) {
        gpio_put(PIN_STROBE, 1);
        busy_wait_us_32((uint32_t)cfg.pulse_us);
        gpio_put(PIN_STROBE, 0);
        printf("{\"type\":\"flash\"}\n");
    }
}

int main(void) {
    stdio_init_all();
    lm_default_cfg(&cfg);

    gpio_init(PIN_STROBE);
    gpio_set_dir(PIN_STROBE, GPIO_OUT);
    gpio_put(PIN_STROBE, 0);
    for (int i = 0; i < N_CAM_PINS; i++) {
        gpio_init(PIN_CAM_FIRST + i);
        gpio_set_dir(PIN_CAM_FIRST + i, GPIO_OUT);
    }
    cams_set(false);
    gpio_init(PIN_GATE1);
    gpio_init(PIN_GATE2);
    gpio_set_irq_enabled_with_callback(PIN_GATE1, GPIO_IRQ_EDGE_RISE, true, &gate_irq);
    gpio_set_irq_enabled(PIN_GATE2, GPIO_IRQ_EDGE_RISE, true);

    char line[64];
    size_t len = 0;
    printf("{\"type\":\"ready\"}\n");
    while (true) {
        if (got_gate2) {
            fire(t_gate1, t_gate2);
            got_gate1 = got_gate2 = false;
        } else if (got_gate1 && time_us_64() - t_gate1 > GATE_TIMEOUT_US) {
            got_gate1 = false;  // gate 1 tripped by something that wasn't a swing
        }
        int c = getchar_timeout_us(0);
        if (c == PICO_ERROR_TIMEOUT) continue;
        if (c == '\n' || c == '\r') {
            line[len] = 0;
            if (len) handle_command(line);
            len = 0;
        } else if (len < sizeof(line) - 1) {
            line[len++] = (char)c;
        }
    }
}
