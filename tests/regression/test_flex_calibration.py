"""Replay the measured USB poses and check current firmware/collector calibration parity."""
import csv
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FlexCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "firmware/demo_latest/GloveDemo/GloveApp.h").read_text()
        cls.bend = list(map(int, re.search(r"BEND\[3\]=\{([\d,]+)\}", cls.source)[1].split(",")))
        cls.release = list(map(int, re.search(r"RELEASE\[3\]=\{([\d,]+)\}", cls.source)[1].split(",")))

    def test_replay_recorded_relaxed_and_fist_poses(self):
        states = [False] * 3
        count = 0
        with (ROOT / "calibration/reference_20261023/readings.csv").open() as f:
            for row in csv.DictReader(f):
                expected = row["pose"] == "fist"
                for i, name in enumerate(("thumb", "index", "middle")):
                    raw = int(row[name])
                    states[i] = raw > self.release[i] if states[i] else raw >= self.bend[i]
                    self.assertEqual(states[i], expected, (row["repeat"], name))
                count += 1
        self.assertEqual(count, 240)

    def test_middle_sensor_is_measured_and_required(self):
        self.assertIn("for(int i=0;i<3;i++){analogRead(FLEX_PINS[i]);", self.source)
        self.assertIn("for(int i=0;i<3;i++)fist=fist&&bent[i]", self.source)
        self.assertNotIn("r.fingers[2]=0", self.source)
        self.assertNotIn("ACTIVE_FLEX_COUNT=2", self.source)

    def test_collector_uses_identical_thresholds_and_new_profile(self):
        folder = ROOT / "collectors/glove_latest"
        settings = json.loads((folder / "sensor_settings.json").read_text())
        sketch = (folder / "MBF_v1/MBF_v1.ino").read_text()
        definitions = json.loads((folder / "gestures.json").read_text())
        for i, name in enumerate(("thumb", "index", "middle")):
            self.assertEqual(settings["flex_diagnostics"][name]["bend_threshold"], self.bend[i])
            self.assertEqual(settings["flex_diagnostics"][name]["release_threshold"], self.release[i])
            self.assertRegex(sketch, rf"FLEX_{name.upper()}_BENT_THRESHOLD\s*=\s*{self.bend[i]};")
        self.assertEqual(definitions["clip_ms"], 3000)
        self.assertEqual(definitions["calibration_id"], settings["calibration_id"])
        self.assertIn("binary_flex_v6", sketch)
        self.assertIn("binary_flex_v6", (folder / "dataset_tools.py").read_text())


if __name__ == "__main__":
    unittest.main()
