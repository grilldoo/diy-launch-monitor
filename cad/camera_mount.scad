// Camera mount for 2020 aluminium extrusion. The camera bolts on with its 1/4"-20 tripod
// adapter (supplied with the Pi Global Shutter camera). The platform is pre-tilted
// to the rig's pitch, and its back fence is turned to the toe-in (yaw) angle, so the
// cameras point roughly at the right spot. Stereo calibration measures the exact pose
// afterwards, so a degree or two of error doesn't matter.
//
// UNVERIFIED: check the tripod adapter's footprint against a real camera before printing all of them.
//
// Angles per camera come from the rig geometry (cad/generated/rig_angles.scad).
// Print: PETG, flat side down, 4 walls, 40% infill, no supports.
// Screws: 2x M5x10 + 2020 T-nuts; 1x 1/4"-20 x 5/8" into the camera's tripod adapter
// (9 mm of plastic + ~6 mm of thread; check the adapter's thread depth so it can't hit the PCB).
include <generated/rig_angles.scad>

cam = 0;                 // index into cams[] (generated): 0 = A, 1 = B, 2/3 = stage-2 club pair
yaw = cams[cam][1];
pitch = cams[cam][2];

foot_l = 50;             // along the extrusion
foot_w = 20;             // 2020 profile width
foot_t = 6;
m5_d = 5.4;
m5_head_d = 9.5;
m5_spacing = 30;
plat = 42;               // camera platform (square), overhangs the extrusion
plat_t = 7;
tripod_d = 6.7;          // 1/4"-20 clearance
tripod_head_d = 12.5;
fence_h = 4;
fence_t = 3;
$fn = 64;

module platform_top() {
    // plate in its own tilted frame: top surface at z = 0
    rotate([0, 0, yaw]) translate([-plat / 2, -plat / 2, -plat_t]) cube([plat, plat, plat_t]);
}

module fence() {
    rotate([0, 0, yaw]) translate([-plat / 2, -plat / 2 - fence_t + 0.5, -2]) cube([plat, fence_t, fence_h + 2]);
}

center = [0, foot_w + plat / 2 - 2, foot_t + plat_t + 4];  // back edge clears the M5 heads

difference() {
    union() {
        translate([-foot_l / 2, 0, 0]) cube([foot_l, foot_w, foot_t]);
        // Solid down to the bed under the whole platform: printable without supports.
        hull() {
            translate([-plat / 2, foot_w - 8, 0]) cube([plat, 8, foot_t]);
            linear_extrude(1) projection() translate(center) rotate([pitch, 0, 0]) platform_top();
            translate(center) rotate([pitch, 0, 0]) platform_top();
        }
        translate(center) rotate([pitch, 0, 0]) fence();
    }
    for (x = [-m5_spacing / 2, m5_spacing / 2])
        translate([x, foot_w / 2, -1]) {
            cylinder(d = m5_d, h = 50);
            translate([0, 0, foot_t + 1 - 0.01]) cylinder(d = m5_head_d, h = 50);  // head seats on the foot
        }
    translate(center) rotate([pitch, 0, 0]) {
        translate([0, 0, -60]) cylinder(d = tripod_d, h = 70);
        translate([0, 0, -60 - plat_t - 2]) cylinder(d = tripod_head_d, h = 60);
    }
}
