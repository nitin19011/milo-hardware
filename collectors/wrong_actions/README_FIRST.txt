MILO - FAST WRONG-ACTION COLLECTION

NO QUOTA. NO AUTOMATIC COMMAND CHANGE. NO FIXED THREE-SECOND CLIPS.
Record as many examples as you want (25, 40, more), then click Next command.

USE YOUR CURRENT GLOVE - NORMALLY NO REFLASH NEEDED
1. Close the old collector/live-detector UI so it releases the COM/UDP port.
2. Run START_WRONG_COLLECTION.bat.
3. Choose Wi-Fi or USB and Connect, using the same settings as before.
This accepts the original MILO1 logger and v1/v2 detector streams (MILO2/MILO3).
The glove's detector may keep running, but its predictions do not accept/reject
or trigger samples in this tool. Only your manual marks define the recordings.
No mic or MQTT broker is needed. Motor stays off with the compatible firmware.
If you have none of those sketches installed, a fallback logger is provided
under optional_firmware/GloveCandidateLogger. It needs ArduinoJson.

RECORD
- Select the intended command, e.g. Sit.
- Press Space BEFORE moving.
- Do an intentionally WRONG version, e.g. point up or extend all fingers.
- Press Space AFTER finishing. The wrong take saves immediately.
- Repeat as many times as you want. There is no 20-take limit.
- Click Next command only when YOU want to move on. You can also click any of
  the seven command buttons or use keys 1..7 to revisit it.
- Esc cancels the current take. Backspace discards the last one.
- No countdown, forced pause, playback or per-take accept screen.
- End session & ZIP automatically finishes an active bracket and exports in the
  background. Closing the window saves too, discarding unfinished active marks.

MISTAKE SUGGESTIONS ARE OPTIONAL
Suggest variations cycles through example ideas every four accepted takes.
It does NOT cap the number of samples or force a particular mistake. Turn it
off to repeat the same mistake, choose another suggestion, or type your own
description in the Mistake box (press Enter afterwards to return keyboard focus).
The large instruction line tells you the current suggestion.
Only collect variants that your team actually considers wrong for that command;
suggestions are prompts, not an automatic proof that an action is invalid.

ACTUALLY ANOTHER VALID GESTURE?
Leave this as unknown if unsure. If a wrong Sit attempt is really a valid Paw,
you can select paw. It should not automatically become a global background
sample. Choose no_valid_command only when it is clearly invalid for all commands.
This optional field does not slow down normal collection.

SAVE / SEND
Send the ZIP shown at the bottom:
  datasets/Milo_Wrong_Actions_<session>.zip

WHAT YOUR AI TEAMMATE GETS
wrong_examples/sit/, wrong_examples/come/, etc.: variable-length nine-column CSVs
and matching JSON metadata. Each CSV is one wrong attempt for that target.
Six IMU axes + three binary finger states; raw ADC is diagnostic, not a feature.
There is no padding, stretching or automatic conversion to a three-second clip.
manifest.csv lists the target, mistake, duration, sample count and file.
wrong_examples.npz contains flat values plus row_splits for variable-length samples.
stream.csv keeps the continuous sensor diagnostics; events.json preserves marks.
README_AI.txt inside each dataset explains labels and how to load the files.

ACCEPTED / VALID HERE MEANS SENSOR DATA QUALITY, NOT A CORRECT ACTION.
Faulty, clipped, incomplete or accidental very short marks do not count as saved
training takes, but their raw readings remain. The tool does not decide whether
you actually performed the intended mistake: that is your label.

IMPORTANT LABEL SCOPE
These are intentional WRONG attempts for the final gesture recognizer/rejection
logic. They are different from everyday no-command activity. Do not automatically
teach the glove's local candidate detector to discard them: an incorrect attempt
may still need to reach Ultra96 to generate voice/gesture mismatch feedback.
Each sample explicitly records is_correct_for_intended=False and the intended
class. Global final-class labels remain unknown unless you select them.

CURRENT ACQUISITION
50 Hz, acceleration m/s^2 including gravity, gyro rad/s without bias subtraction.
Finger order thumb/index/middle; states exactly 0 NOT_BENT / 1 BENT.
23 Oct calibration: bend 1696/1920/3520, release 1583/1762/3487.
Variable samples are operator brackets, not precisely measured physical onset.
The AI teammate can later crop/pad/resample according to her model; binary
states must not be interpolated as continuous angles.

Wi-Fi uses local unencrypted UDP 25400; USB uses 230400 baud. Previous Wi-Fi
configuration on the glove can be reused. Your original projects, firmware,
earlier recordings and their ZIPs are not edited by this package.

Tests: py -3 -m unittest test_wrong test_collector
