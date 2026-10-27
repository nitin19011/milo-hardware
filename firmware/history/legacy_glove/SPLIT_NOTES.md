# Glove/collar split — 16 Sep 2026

MBF_v1 now runs the glove MPU6050 and three flex sensors only. It no longer initializes I2S or publishes microphone packets. Pin assignments, thresholds, motion packet format and Wi-Fi/MQTT settings are preserved.

The previous combined firmware is backed up as `MBF_v1.before_collar_2026-09-16.ino.bak`. Do not rename that backup to another `.ino` inside this sketch folder; Arduino could compile both files together.

The new collar firmware, recording/training scripts, wiring and test steps are in `../Collar_System/START_HERE.md`. Both ESPs connect directly to the laptop broker. No microphone cable or ESP-to-ESP relay is needed between glove and collar.

Known existing issue: Adafruit_MPU6050::getEvent() in the installed library returns true without propagating I2C read failure. The glove's existing imu.valid field therefore does not reliably detect bad reads. This split preserves sensor behavior and corrects the misleading comment only. Earlier abnormal MPU readings and the index flex channel stuck at 4095 still need a separate diagnosis/fix.

Each board's timestamp_us is independent boot-relative time, not a shared synchronization clock.
