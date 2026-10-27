# Validation — 16 Sep 2026

Completed:

- Compared updated MBF_v1 with its exact backup: removed only microphone functionality, updated startup text, and corrected the misleading MPU validity comment. Existing sensor settings/packets and network settings remain intact.
- Backup SHA256: `6F7596402538F958FE5D390F671B91F278447E8A10ABA92942291993A0270FB1`.
- Source/object compilation passed for glove MBF_v1, collar Collar_Mic, and Collar_Recorder using installed Arduino-ESP32 3.3.11, original ESP32/FireBeetle definitions and installed libraries.
- A separate Collar_Mic copy with synthetic template data also passed source/object compilation, exercising the enabled detector. The actual delivered header remains UNTRAINED; synthetic templates were not installed as your wake-word model.
- Six Python tests passed: sound features, synthetic matching/silence rejection, complete WAV reconstruction, corrupt/missing/incomplete clip rejection, rejection of other-device topics/source IDs, and synthetic training/export/evaluation targeting Collar_Mic/milo_model.h.
- Training tool command-line help runs successfully. Synthetic test artifacts remain separate under test_output; they are not your voice recordings.

Not completed:

- Full Arduino linking/flash-image generation and upload. A normal Arduino CLI build failed before compilation because esptool could not extract VCRUNTIME140.dll (permission denied). Source checks used the installed compiler directly with Arduino include/configuration flags; no claim of a successful full build is made.
- No code was flashed, no physical microphone was recorded, and no live MQTT session was started or modified.
- Real voice accuracy, runtime heap, audio timing, independent operation of both boards and network recovery still need your bench tests.
- The pre-existing glove MPU/flex problems were not repaired as part of this split. The optional matcher retains the prototype limitations described in START_HERE.md.
