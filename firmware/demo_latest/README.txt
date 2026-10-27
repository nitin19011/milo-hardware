CURRENT DEMO - 23 OCTOBER 2026

Open the repository README.md for configuration and flashing instructions.
GloveDemo/GloveDemo.ino: all three flex sensors enabled. Hold thumb, index AND middle bent 2 seconds; 1-second cue, 3-second paired capture, 1-second finishing cue, then upload.
New bend thresholds: 1696 / 1920 / 3520. Release: 1583 / 1762 / 3487.
MicDemo/MicDemo.ino: same MLW1/WAV audio and capture-control protocol. No mic reflash required solely for the glove threshold update.
CALIBRATION_20261023.json is authoritative for this update. Earlier dated diagnostic notes and real-log examples are historical.
Private passwords are absent: configure demo_settings.local.json from the example, then run CONFIGURE_DEMO.bat.
