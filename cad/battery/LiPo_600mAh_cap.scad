// Matching external cap for the supplied sleeve; units: mm.
// Exported STLs are already oriented with the end face on the print bed.
clearance = 0.20; // per side; looser version uses 0.35
wall = 1.6;
overlap = 8;
wire_width = 6;
module cap() {
 difference() {
  translate([-clearance-wall,-wall,-clearance-wall])
   cube([28.2+2*(clearance+wall),overlap+wall,9.9+2*(clearance+wall)]);
  translate([-clearance,0,-clearance])
   cube([28.2+2*clearance,overlap+1,9.9+2*clearance]);
  translate([(28.2-wire_width)/2,-wall-1,4.95])
   cube([wire_width,overlap+wall+2,10]);
 }
}
translate([clearance+wall,9.9+clearance+wall,wall]) rotate([90,0,0]) cap();
