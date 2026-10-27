// Strobe/exposure schedule. Pure C, no SDK dependencies, so it builds and is
// unit-tested on the host. Mirrored in src/launchmonitor/schedule.py; keep the
// two in sync (tests/test_schedule_parity.py checks them against each other).
#ifndef LM_TIMING_H
#define LM_TIMING_H

#include <stdbool.h>
#include <stdint.h>

#define LM_MAX_CLUB_FLASHES 4
#define LM_MAX_BALL_FLASHES 8
#define LM_MAX_FLASHES (LM_MAX_CLUB_FLASHES + LM_MAX_BALL_FLASHES)

enum { LM_FLASH_CLUB = 0, LM_FLASH_BALL = 1 };

typedef struct {
    double gate1_m, gate2_m;  // gate distance behind the ball
    double club_flash_m[LM_MAX_CLUB_FLASHES];  // club distance before impact
    int n_club;
    double ball_spacing_m;
    int n_ball;
    double smash_est;
    int64_t pulse_us;
    int64_t exposure_lead_us;    // exposure opens this long before the first flash
    int64_t exposure_margin_us;  // and closes this long after the last
    int64_t min_lead_us;
    double min_speed, max_speed;  // m/s
} lm_timing_cfg_t;

typedef struct {
    bool ok;
    const char *error;
    double club_speed;  // m/s
    int64_t t_impact_us;
    int n_flashes;
    int64_t flash_us[LM_MAX_FLASHES];
    uint8_t flash_kind[LM_MAX_FLASHES];
    int64_t exposure_start_us, exposure_end_us;
} lm_schedule_t;

void lm_default_cfg(lm_timing_cfg_t *cfg);
bool lm_compute_schedule(const lm_timing_cfg_t *cfg, int64_t t1_us, int64_t t2_us, lm_schedule_t *out);

#endif
