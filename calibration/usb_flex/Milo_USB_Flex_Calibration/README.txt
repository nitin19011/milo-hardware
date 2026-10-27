USB-ONLY FLEX CALIBRATION

1. Open Flex_USB_Calibration/Flex_USB_Calibration.ino in Arduino IDE.
2. Select FireBeetle-ESP32 and the glove's USB port, then upload.
3. CLOSE Serial Monitor / Serial Plotter so the collector can use the port.
4. Leave USB connected, wear the glove, and run START_CALIBRATION.bat.
5. Follow the relaxed hand / comfortable fist prompts for three rounds.
   Get into each pose before pressing Enter. Hold still until it says saved.
6. Send the ZIP under results to review the thresholds.

Uses only raw flex ADC on thumb GPIO35, index GPIO34 and middle GPIO39.
No Wi-Fi, MQTT, mic, IMU, motor, or existing bent-state thresholds.
Uses the same ADC attenuation and 8-reading average as the demo firmware.

Each pose records 4 seconds after a 0.7-second settling interval.
Reports thresholds only when repeated relaxed/bent readings separate adequately.
Both thumb/index and the replacement middle sensor are recalibrated.
Your current demo files and their thresholds are NOT changed automatically.
This replaces the running sketch on the glove; reflash demo firmware afterwards.

Results: results/<timestamp>/readings.csv, calibration.json, summary.txt
Send: results/<timestamp>.zip
If no serial ports appear, check the USB data cable/driver.
If port access is denied, close any application already using that serial port.
If you have several ports, choose the glove's port from the printed list.
Only Python 3 and pyserial are needed. The BAT installs pyserial if absent.
