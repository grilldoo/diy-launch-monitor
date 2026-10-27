// Camera mount for 2020 aluminium extrusion, for the InnoMaker CAM-IMX296Mono-GS board
// (39 x 39 mm, four holes on a 34 mm square, per InnoMaker's manual V2.0.2). The board
// screws onto four bosses on an upright plate. The plate is pre-tilted to the rig's pitch
// and turned to its toe-in (yaw), so the camera points roughly at the right spot. Stereo
// calibration measures the exact pose afterwards, so a degree or two of error doesn't matter.
//
// UNVERIFIED: the manual doesn't give the board's hole diameter. M2 screws fit M2 and
// M2.5 holes, so use M2 x 8 self-tapping screws into the bosses.
//
// Angles per camera come from the rig geometry (cad/generated/rig_angles.scad).
// Print: PETG, foot flat on the bed, 4 walls, 40% infill, no supports.
// Screws: 2x M5x10 + 2020 T-nuts; 4x M2x8 self-tapping (camera board).
include <generated/rig_angles.scad>

cam = 0;                 // index into cams[] (generated): 0 = A, 1 = B, 2/3 = stage-2 club pair
yaw = cams[cam][1];
pitch = cams[cam][2];

foot_l = 84;             // along the extrusion; screws sit outside the plate so they stay reachable
foot_w = 20;             // 2020 profile width
foot_t = 6;
m5_d = 5.4;
m5_head_d = 9.5;
m5_spacing = 68;
plate = 44;              // square, covers the 39 mm board
plate_t = 5;
hole_sq = 34;            // board mounting-hole square
boss_d = 5.5;
boss_h = 4;              // clearance for parts on the back of the board
pilot_d = 1.7;           // M2 self-tapping
$fn = 48;

// Plate centre = sensor centre. +Y is the camera's viewing direction.
center = [0, foot_w / 2, foot_t + plate / 2 + 4];

module oriented() {
    translate(center) rotate([0, 0, yaw]) rotate([pitch, 0, 0]) children();
}

module plate_shape() {
    oriented() translate([-plate / 2, -plate_t, -plate / 2]) cube([plate, plate_t, plate]);
}

difference() {
    union() {
        translate([-foot_l / 2, 0, 0]) cube([foot_l, foot_w, foot_t]);
        // Solid down to the foot behind the plate: stiff and printable without supports.
        hull() {
            plate_shape();
            linear_extrude(1) projection() plate_shape();
        }
        oriented() for (x = [-1, 1], z = [-1, 1])
            translate([x * hole_sq / 2, -0.01, z * hole_sq / 2]) rotate([-90, 0, 0])
                cylinder(d = boss_d, h = boss_h);
    }
    for (x = [-m5_spacing / 2, m5_spacing / 2])
        translate([x, foot_w / 2, -1]) {
            cylinder(d = m5_d, h = 50);
            translate([0, 0, foot_t + 1 - 0.01]) cylinder(d = m5_head_d, h = 50);  // head seats on the foot
        }
    oriented() for (x = [-1, 1], z = [-1, 1])
        translate([x * hole_sq / 2, boss_h + 0.1, z * hole_sq / 2]) rotate([90, 0, 0])
            cylinder(d = pilot_d, h = boss_h + 10);
}
