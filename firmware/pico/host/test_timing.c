// Host unit tests for lm_timing.c. Build and run: make -C firmware/pico/host test
#include <stdio.h>
#include <stdlib.h>

#include "lm_timing.h"

static int failures = 0;
#define CHECK(cond)                                                 \
    do {                                                            \
        if (!(cond)) {                                              \
            fprintf(stderr, "%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #cond); \
            failures++;                                             \
        }                                                           \
    } while (0)

static void test_typical_driver(void) {
    lm_timing_cfg_t cfg;
    lm_schedule_t s;
    lm_default_cfg(&cfg);
    // 45 m/s club: gates 0.13 m apart -> 2889 us.
    CHECK(lm_compute_schedule(&cfg, 1000000, 1002889, &s));
    CHECK(s.club_speed > 44.9 && s.club_speed < 45.1);
    CHECK(s.t_impact_us == 1002889 + 2667);
    CHECK(s.n_flashes == 8);
    for (int i = 1; i < s.n_flashes; i++) CHECK(s.flash_us[i] > s.flash_us[i - 1] + cfg.pulse_us);
    CHECK(s.flash_kind[0] == LM_FLASH_CLUB && s.flash_kind[2] == LM_FLASH_CLUB);
    CHECK(s.flash_kind[3] == LM_FLASH_BALL);
    CHECK(s.flash_us[2] < s.t_impact_us && s.flash_us[3] > s.t_impact_us);
    CHECK(s.exposure_start_us < s.flash_us[0] && s.exposure_end_us > s.flash_us[7]);
}

static void test_fast_swing_drops_early_flash(void) {
    lm_timing_cfg_t cfg;
    lm_schedule_t s;
    lm_default_cfg(&cfg);
    cfg.min_lead_us = 1000;  // pretend the Pico is slow to react
    CHECK(lm_compute_schedule(&cfg, 0, 1857, &s));  // ~70 m/s
    CHECK(s.n_flashes < 8);
    for (int i = 0; i < s.n_flashes; i++) CHECK(s.flash_us[i] >= 1857 + 1000 + cfg.exposure_lead_us);
}

static void test_rejects_bad_input(void) {
    lm_timing_cfg_t cfg;
    lm_schedule_t s;
    lm_default_cfg(&cfg);
    CHECK(!lm_compute_schedule(&cfg, 100, 100, &s));
    CHECK(!lm_compute_schedule(&cfg, 0, 1000000, &s));  // 0.13 m/s: not a swing
    CHECK(!lm_compute_schedule(&cfg, 0, 100, &s));  // 1300 m/s: noise
}

int main(void) {
    test_typical_driver();
    test_fast_swing_drops_early_flash();
    test_rejects_bad_input();
    if (failures) {
        fprintf(stderr, "%d failure(s)\n", failures);
        return 1;
    }
    printf("lm_timing: all tests passed\n");
    return 0;
}
