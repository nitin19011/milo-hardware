import csv
import io
import json
from pathlib import Path
import queue
import socket
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch
import zipfile

from collector_core import Connection, Frame, Session, configure_wifi, parse_packet

BOOT = "0123456789abcdef"
HOST = 1_000_000_000_000


class TempFixture:
    # Workspace fixtures inherit normal Windows ACLs; excluded from the deliverable.
    def __init__(self):
        root = Path(__file__).resolve().parent / ".test_output" / uuid.uuid4().hex
        root.mkdir(parents=True)
        self.name = str(root)

    def cleanup(self):
        pass


def packet(seq=0, boot=BOOT):
    return (f"MILO1,{boot},{seq},{1000000+seq*20000},0,0,9.80665,0.1,0.2,0.3,0,1,0,1450,2200,3458,1,0,0,0,0\n").encode()


def frame(seq, boot=BOOT, rails=0, clipped=0, base=HOST):
    f = parse_packet(packet(seq, boot), "USB", host_ns=base+seq*20_000_000, utc_ns=base+seq*20_000_000)
    f.rails, f.clipped = rails, clipped
    return f


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TempFixture()
        self.session = Session(self.temp.name)

    def tearDown(self):
        self.session.close_input()
        self.temp.cleanup()

    def feed(self, start, end, **kwargs):
        for seq in range(start, end): self.session.ingest(frame(seq, **kwargs))

    def test_packet_and_feature_validation(self):
        f = parse_packet(packet(), "Wi-Fi")
        self.assertEqual(f.features[6:], (0, 1, 0))
        self.assertEqual(f.raw, (1450, 2200, 3458))
        self.assertIsNone(parse_packet(b"#CONFIG_OK\n", "USB"))
        self.assertIsNone(parse_packet(packet().replace(b"9.80665", b"nan"), "USB"))
        self.assertIsNone(parse_packet(packet().replace(b",1450,", b",5000,"), "USB"))

    def test_continuous_export_context_and_neighbour_labels(self):
        s = self.session
        self.feed(0, 10)
        s.start("gesture", "come", HOST+190_000_000)
        self.feed(10, 40)
        first = s.finish(HOST+790_000_000)
        self.assertTrue(first["accepted"])
        s.start("gesture", "sit", HOST+795_000_000)
        self.feed(40, 70)
        second = s.finish(HOST+1_390_000_000)
        self.assertTrue(second["accepted"])
        s.start("background", "typing", HOST+1_395_000_000)
        self.feed(70, 140)
        negative = s.finish(HOST+2_790_000_000)
        self.assertTrue(negative["accepted"])
        archive = s.export()
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip())
            self.assertIn("stream.csv", z.namelist())
            clips = [n for n in z.namelist() if n.startswith("gesture_clips/come/") and n.endswith(".csv")]
            rows = list(csv.DictReader(io.StringIO(z.read(clips[0]).decode())))
            self.assertTrue(any(second["id"] in r["other_gesture_ids"] for r in rows))
            self.assertTrue(any(r["inside_target_bracket"] == "1" for r in rows))
            self.assertEqual(json.loads(z.read("session.json"))["stats"]["received"], 140)
            self.assertEqual(len(list(csv.DictReader(io.StringIO(z.read("stream.csv").decode())))), 140)

    def test_faulty_gesture_rejected_and_raw_data_retained(self):
        self.feed(0, 10)
        self.session.start("gesture", "come", HOST+190_000_000)
        self.feed(10, 20)
        self.session.ingest(frame(20, rails=4))
        self.feed(21, 40)
        event = self.session.finish(HOST+790_000_000)
        self.assertFalse(event["accepted"])
        self.assertIn("flex_rail", event["quality"]["issues"])
        self.assertEqual(len(self.session.frames), 40)

    def test_gap_background_retained_with_window_filter_flag(self):
        self.feed(0, 10)
        self.session.start("background", "walking", HOST+190_000_000)
        self.feed(10, 20); self.feed(21, 40)
        event = self.session.finish(HOST+790_000_000)
        self.assertTrue(event["accepted"])
        self.assertTrue(event["requires_window_quality_filter"])
        self.assertEqual(self.session.stats["missing_samples"], 1)

    def test_restart_and_stale_markers_cannot_be_clean_takes(self):
        self.feed(0, 10)
        self.session.start("gesture", "come", HOST+190_000_000)
        self.feed(10, 25, boot="fedcba9876543210")
        e = self.session.finish(HOST+490_000_000)
        self.assertFalse(e["accepted"])
        self.assertIn("device_restarted", e["quality"]["issues"])
        with self.assertRaises(ValueError): self.session.start("gesture", "come", HOST+3_000_000_000)

    def test_long_background_survives_reboot_with_quality_flag(self):
        self.feed(0, 10)
        self.session.start("background", "mixed_everyday", HOST+190_000_000)
        self.feed(10, 25)
        self.feed(25, 40, boot="fedcba9876543210")
        event = self.session.finish(HOST+790_000_000)
        self.assertTrue(event["accepted"])
        self.assertTrue(event["requires_window_quality_filter"])
        self.assertIn("device_restarted", event["quality"]["issues"])

    def test_cancel_discard_and_autosaved_annotations(self):
        self.feed(0, 10)
        self.session.start("gesture", "come", HOST+190_000_000)
        self.session.cancel()
        self.assertEqual(json.loads((self.session.folder/"events.json").read_text())[0]["status"], "discarded")
        self.session.start("gesture", "come", HOST+195_000_000)
        self.feed(10, 40)
        self.session.finish(HOST+790_000_000)
        self.assertEqual(self.session.snapshot()["counts"]["come"], 1)
        self.session.discard()
        self.assertEqual(self.session.snapshot()["counts"]["come"], 0)

    def test_real_udp_transport(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
        ready, got = threading.Event(), threading.Event()
        received, statuses = [], []
        def on_frame(f):
            received.append(f)
            if len(received) == 20: got.set()
        def on_status(text):
            statuses.append(text); ready.set()
        connection = Connection("Wi-Fi", "", on_frame, on_status, udp_port=port)
        connection.start()
        try:
            self.assertTrue(ready.wait(3))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                for seq in range(20): sender.sendto(packet(seq), ("127.0.0.1", port))
            self.assertTrue(got.wait(3), statuses)
            self.assertEqual([f.seq for f in received], list(range(20)))
        finally:
            connection.stop(); connection.thread.join(2)

    def test_wifi_configuration_ack_without_echo(self):
        class FakeSerial:
            def __init__(self, *args, **kwargs): self.sent = False
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def readline(self): return b"#CONFIG_OK\n" if self.sent else packet()
            def write(self, value):
                d = json.loads(value)
                assert d["cmd"] == "wifi" and d["host"] == "192.168.1.2"
                self.sent = True
            def flush(self): pass
        with patch("serial.Serial", FakeSerial):
            configure_wifi("COM_TEST", "test-hotspot", "test-only", "192.168.1.2")


class UITests(unittest.TestCase):
    def test_fast_controls_counts_keyboard_and_layout(self):
        import tkinter as tk
        import collector_ui
        temp = TempFixture()
        root = tk.Tk()
        with patch.object(collector_ui, "RESULTS", Path(temp.name)):
            app = collector_ui.App(root)
            root.update()
            app.new_session(); app.target.set(1)
            now = time.monotonic_ns(); base = now-2_000_000_000
            for seq in range(51): app.session.ingest(frame(seq, base=base))
            app.session.start("gesture", "come", base+1_000_000_000)
            for seq in range(51, 100): app.session.ingest(frame(seq, base=base))
            app.last_toggle = 0; app.toggle()
            self.assertEqual(app.session.snapshot()["counts"]["come"], 1)
            self.assertEqual(app.selected, 0)
            app.undo()
            self.assertEqual(app.session.snapshot()["counts"]["come"], 0)
            self.assertEqual(app.selected, 0)
            app.mode.set("background"); app.mode_changed()
            self.assertEqual(app.mode.get(),"gesture")
            app.next_command();self.assertEqual(app.selected,1)
            app.choose(0)
            entries = []
            def visit(w):
                for child in w.winfo_children():
                    if child.winfo_class() == "TEntry": entries.append(child)
                    visit(child)
            visit(root)
            with patch.object(root, "focus_get", return_value=entries[0]):
                self.assertIsNone(app.key_space(None))
                self.assertIsNone(app.session.active)
            app.end_session()
            message = app.messages.get(timeout=3)
            self.assertEqual(message[0], "exported")
            app.messages.put(message); app.poll(); root.update()
            self.assertIsNone(app.session)
            self.assertTrue(app.last_zip.is_file())
            self.assertIn("SEND THIS ZIP", app.saved.get())
            app.wifi_dialog(); root.update()
            popup = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            buttons = [w for w in popup.winfo_children()[0].winfo_children() if w.winfo_class() == "TButton"]
            self.assertTrue(buttons[0].winfo_ismapped())
            self.assertLess(buttons[0].winfo_rooty()+buttons[0].winfo_height(), popup.winfo_rooty()+popup.winfo_height())
            popup.destroy()
            bottom = app.status_label.winfo_y()+app.status_label.winfo_height()
            print("UI layout:", root.winfo_width(), root.winfo_height(), "status bottom", bottom)
            self.assertTrue(app.status_label.winfo_ismapped())
            self.assertTrue(app.saved_label.winfo_ismapped())
            self.assertLess(bottom + 25, root.winfo_height(), "Status and ZIP path must fit without scrolling")
            root.destroy()
        temp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
