#include "lm_timing.h"

#include <math.h>
#include <string.h>

static int64_t round_half_up(double x) { return (int64_t)floor(x + 0.5); }

void lm_default_cfg(lm_timing_cfg_t *cfg) {
    memset(cfg, 0, sizeof(*cfg));
    cfg->gate1_m = 0.25;
    cfg->gate2_m = 0.12;
    cfg->club_flash_m[0] = 0.09;
    cfg->club_flash_m[1] = 0.05;
    cfg->club_flash_m[2] = 0.015;
    cfg->n_club = 3;
    cfg->ball_spacing_m = 0.06;
    cfg->n_ball = 5;
    cfg->smash_est = 1.35;
    cfg->pulse_us = 15;
    // The InnoMaker camera's trigger goes through an optocoupler whose turn-off delay
    // (= exposure start) is tens of microseconds and varies per unit, so open early.
    cfg->exposure_lead_us = 300;
    cfg->exposure_margin_us = 50;
    cfg->min_lead_us = 150;
    cfg->min_speed = 8.0;
    cfg->max_speed = 75.0;
}

static bool fail(lm_schedule_t *out, const char *err) {
    out->ok = false;
    out->error = err;
    return false;
}

bool lm_compute_schedule(const lm_timing_cfg_t *cfg, int64_t t1_us, int64_t t2_us, lm_schedule_t *out) {
    memset(out, 0, sizeof(*out));
    int64_t dt = t2_us - t1_us;
    if (dt <= 0) return fail(out, "gate order");
    double v = (cfg->gate1_m - cfg->gate2_m) / ((double)dt * 1e-6);
    out->club_speed = v;
    if (v < cfg->min_speed || v > cfg->max_speed) return fail(out, "speed out of range");

    int64_t t_impact = t2_us + round_half_up(cfg->gate2_m / v * 1e6);
    int64_t earliest = t2_us + cfg->min_lead_us + cfg->exposure_lead_us;
    int n = 0;
    for (int i = 0; i < cfg->n_club && i < LM_MAX_CLUB_FLASHES; i++) {
        int64_t t = t_impact - round_half_up(cfg->club_flash_m[i] / v * 1e6);
        if (t >= earliest) {  // too-fast swings drop the earliest club flash rather than fail
            out->flash_us[n] = t;
            out->flash_kind[n++] = LM_FLASH_CLUB;
        }
    }
    if (n == 0) return fail(out, "no club flash fits");

    int64_t ball_dt = round_half_up(cfg->ball_spacing_m / (cfg->smash_est * v) * 1e6);
    for (int k = 0; k < cfg->n_ball && k < LM_MAX_BALL_FLASHES; k++) {
        out->flash_us[n] = t_impact + (k + 1) * ball_dt;
        out->flash_kind[n++] = LM_FLASH_BALL;
    }

    out->ok = true;
    out->error = "";
    out->t_impact_us = t_impact;
    out->n_flashes = n;
    out->exposure_start_us = out->flash_us[0] - cfg->exposure_lead_us;
    out->exposure_end_us = out->flash_us[n - 1] + cfg->pulse_us + cfg->exposure_margin_us;
    return true;
}
