# Full-WAV validation — 16 Sep 2026

Passed:
- The collar's current SSID, password and broker IP were preserved from its edited source.
- Seven Python tests: sound features, synthetic matching, full 128,044-byte WAV saved unchanged, malformed/incomplete/oversized WAV rejection, wrong/legacy topics ignored, optional metadata and duplicate-ID protection, and synthetic template export/evaluation.
- Six command-dataset collector tests still pass. Existing datasets/recordings are not used as test fixtures or modified.
- Native C++ capture tests used the actual MiloCapture.h with a deterministic detector stub: rolling-buffer wrap/order for 200 frames, valid maximum-size WAV header, ownership while sending, early silence endpoint, initial short history, age expiry, known I2S-gap abort and connection-epoch invalidation passed.
- That native capture produced a four-second WAV accepted by the actual Python receiver validator.
- Native C++ tests compiled the actual local CollarMqtt.cpp against a fake TCP Client. It emitted ONE correctly framed MQTT PUBLISH containing a byte-identical 128,044-byte WAV using a 1 kB MQTT buffer. Large-length boundary cases (including 65,535/65,536), oversized payload/topic rejection and ordinary retained status publishing passed.
- At the full-WAV validation stage, direct ESP32 source/object compilation passed for the untrained Collar_Mic sketch and local CollarMqtt.cpp. A separate synthetic-template source check exercised the detector-enabled branch. See the subsequent enrollment results below for the current trained model.

Not verified:
- Native tests use simulated time, audio and transport, not a real broker or ESP. They do not measure speech accuracy, task timing, TCP delivery, memory fragmentation or power stability.
- A normal full Arduino CLI build was attempted but stopped at esptool's VCRUNTIME140.dll extraction permission error. No complete linked/uploadable firmware image was verified here.
- No code was flashed, no live broker was started/changed, and no real audio was transmitted.
- Physical-board validation must check post-Wi-Fi free heap, upload time, gaps/resets, real trigger accuracy, clip truncation and commands spoken during the single-buffer upload busy period.
- QoS 0 has no end-to-end delivery acknowledgement or automatic retry. Successful local writes are not proof the AI received/processed the recording.

The full-WAV C++ test harness/artifacts are in the Codex workspace's work/wav_host directory. They contain synthetic data only. That validation stage did not edit the installed global PubSubClient library, glove firmware, recorder firmware, model header or user recordings.

## Milo enrollment — 16 Sep 2026

- Exported model `86b674a15f5b` to `Collar_Mic/milo_model.h`, using seven accepted Milo-only templates, 12 calibration-positive clips and eight calibration-negative clips.
- Preserved the previous model header in `backups/before_milo_enrollment_2026-09-16/milo_model.h`.
- Moved unsuitable template `1789547260532175800.wav` into `recordings/excluded_templates/`; it was not deleted. It had activity from the start and an overly long active span.
- Calibration: zero missed positive clips out of 12, and two false-trigger negative clips out of eight. These clips were used to choose/check the threshold; these figures are not independent test accuracy or a false-alarm rate per hour.
- Exported distance threshold: 0.03349183920306544. Exported RMS gate: 212.60958862304688.
- The actual C++ matcher and exported header were run on all 20 calibration WAVs on the PC. Trigger decisions agreed with Python on every clip; maximum absolute best-score difference was approximately 6.3e-8. This does not validate ESP32 execution timing.
- Direct ESP32 source/object compilation passed for the collar sketch with this real exported model. Full linking/upload and physical-board verification remain outstanding.
- Next: collect fresh `test_positive` and `test_negative` recordings and run `milo.py evaluate`. Do not reuse calibration clips as independent tests. Batches of four are a temporary workaround for the reported seventh-recording failure; its cause remains undiagnosed and recording integrity checks remain enabled.

## Recall-oriented threshold adjustment — 16 Sep 2026

- The first independent batch detected six of eight command clips and triggered on zero of eight non-command clips at threshold 0.03349183920306544.
- With user approval, raised the distance threshold to 0.045, leaving the seven templates and RMS gate unchanged. Exported model: `63aeffbdedfb`.
- Rechecking existing clips at the new threshold: 12/12 calibration commands and 8/8 former test commands trigger. Non-command triggers: 4/8 calibration clips (previously 2/8), and 0/8 former test clips. These are now tuning results, NOT independent accuracy. A trigger anywhere in a clip does not prove correct word timing or complete command capture.
- Previous model/header and available reports are preserved in `backups/before_threshold_adjustment_20260916_164606/`. The new comparison is in `threshold_tuning_report.json`; the old calibration report still describes its original model ID.
- No recordings were moved or deleted. The model records hashes of tuning audio; evaluation excludes matching files, including renamed copies. New recordings can be added to the same test folders, and only fresh files will be scored. Both fresh positive and negative groups are required.
- The exported header still needs uploading to the collar board. No physical-board accuracy or delivery claim is made.
