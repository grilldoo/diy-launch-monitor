// Ball-marking jig: a two-piece shell around the ball with a hole at every pattern dot.
// Assemble around a ball and push three alignment pins (1.75 mm filament, ~6 mm long)
// through both flanges,
// then dot through every hole with a carbon-pigment pen (e.g. Pigma Micron 05).
//
// Hole positions come from src/launchmonitor/data/ball_pattern.json via
// tools/export_cad.py (cad/generated/ball_pattern.scad). Don't edit by hand.
//
// Print: PETG, 0.2 mm layers, 3 walls, each half flange-down. No supports needed
// for the dome; add tree supports only if the very top sags.
include <generated/ball_pattern.scad>

part = "both";            // "top", "bottom", "both" (print layout), "assembled" (preview)

ball_d = 42.67;
clearance = 0.25;         // radial; snug so the ball can't turn while marking
wall = 3.0;
flange_w = 7.0;
flange_t = 3.0;
hole_d = dot_diameter_mm; // at the ball surface
countersink_d = 6.5;      // at the outer surface; guides the pen tip
pin_d = 1.95;             // for 1.75 mm filament
pin_depth = 4.0;
pin_angles = [15, 140, 255];  // uneven, so the halves only fit one way

r_in = ball_d / 2 + clearance;
r_out = r_in + wall;
r_flange = r_out + flange_w;
$fn = 72;

module orient(d) {
    // rotate +Z onto direction d
    rotate([0, acos(d[2] / norm(d)), atan2(d[1], d[0])]) children();
}

// One revolved profile per hole (straight bore, countersink cone, clearance for the
// pen beyond the shell): far faster to render than three separate solids.
module dot_hole() {
    a = r_in + 0.6;
    b = a + wall;
    rotate_extrude($fn = 20)
        polygon([[0, r_in - 2], [hole_d / 2, r_in - 2], [hole_d / 2, a], [countersink_d / 2, b],
                 [countersink_d / 2, r_flange + 5], [0, r_flange + 5]]);
}

module dot_holes() {
    for (d = dots) orient(d) dot_hole();
}

// One half in the assembled frame: upper (z >= 0) or lower (z <= 0).
module half(upper = true) {
    s = upper ? 1 : -1;
    difference() {
        union() {
            intersection() {
                sphere(r = r_out);
                translate([0, 0, s * r_out / 2]) cube([2 * r_out + 1, 2 * r_out + 1, r_out], center = true);
            }
            translate([0, 0, upper ? 0 : -flange_t]) cylinder(r = r_flange, h = flange_t);
        }
        sphere(r = r_in);
        dot_holes();
        for (a = pin_angles)
            rotate([0, 0, a]) translate([(r_out + r_flange) / 2, 0, upper ? -0.01 : -pin_depth])
                cylinder(d = pin_d, h = pin_depth + 0.01, $fn = 24);
        // index notch on the flange edge so you can see which way round the halves go
        rotate([0, 0, pin_angles[0]]) translate([r_flange, 0, 0]) cube([3, 3, 20], center = true);
    }
}

if (part == "assembled") {
    half(true);
    half(false);
} else {
    // Both halves flange-down on the bed.
    if (part == "top" || part == "both") half(true);
    if (part == "bottom" || part == "both")
        translate([part == "both" ? 2 * r_flange + 6 : 0, 0, 0]) rotate([180, 0, 0]) half(false);
}
