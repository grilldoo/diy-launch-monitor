// Host tool: prints the schedule for given gate times as JSON (used by the
// Python parity test). Usage: schedule_cli <t1_us> <t2_us>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#include "lm_timing.h"

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s t1_us t2_us\n", argv[0]);
        return 2;
    }
    lm_timing_cfg_t cfg;
    lm_schedule_t s;
    lm_default_cfg(&cfg);
    lm_compute_schedule(&cfg, strtoll(argv[1], NULL, 10), strtoll(argv[2], NULL, 10), &s);
    printf("{\"ok\":%s,\"error\":\"%s\",\"club_speed\":%.6f,\"t_impact\":%" PRId64 ",\"flashes\":[",
           s.ok ? "true" : "false", s.error, s.club_speed, s.t_impact_us);
    for (int i = 0; i < s.n_flashes; i++)
        printf("%s[%" PRId64 ",%d]", i ? "," : "", s.flash_us[i], s.flash_kind[i]);
    printf("],\"exposure\":[%" PRId64 ",%" PRId64 "]}\n", s.exposure_start_us, s.exposure_end_us);
    return 0;
}
