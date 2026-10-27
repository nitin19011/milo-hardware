import csv
import json
from pathlib import Path
import unittest
import uuid
import zipfile
import time
from collector_core import Session, parse_packet
from test_collector import HOST, BOOT, packet


def model_packet(seq, proposal=0):
    # Proposals at sample 50 (one second) and 100; packet carries their original sequence/time.
    source_seq = 50 if proposal == 1 else 100 if proposal == 2 else 0
    us = 1_000_000 + source_seq*20_000 if proposal else 0
    base = packet(seq).decode().strip().replace("MILO1,", "MILO3,", 1)
    return (base + f",0.200000,{proposal},{us},{source_seq},1,350\n").encode()


class DetectorTests(unittest.TestCase):
    def test_live_ui_displays_actual_glove_score_and_counter(self):
        import tkinter as tk
        from collector_ui import App
        root=tk.Tk();app=App(root)
        now=time.monotonic_ns()
        f=parse_packet(model_packet(70,1),'USB',host_ns=now,utc_ns=now)
        app.latest=f;app.history.append(f);app.poll();root.update()
        self.assertIn('Score 0.20',app.health_text.cget('text'))
        self.assertIn('DETECTOR:',app.detector_label.cget('text'))
        self.assertEqual(f.detector_version,'MILO3')
        f.candidate_score=.7;app.poll();root.update()
        self.assertIn('POSSIBLE ACTION',app.detector_label.cget('text'))
        legacy=parse_packet(model_packet(70,1).replace(b'MILO3,',b'MILO2,'),'USB',host_ns=time.monotonic_ns())
        app.latest=legacy;app.poll();root.update()
        self.assertIn('OLD SKETCH',app.detector_label.cget('text'))
        self.assertEqual(app.split.get(),'validation')
        self.assertEqual(app.target.get(),5)
        self.assertIn('Mark action start',app.record_button.cget('text'))
        root.destroy()

    def test_embedded_telemetry_and_bad_future_marker(self):
        f=parse_packet(model_packet(70,1),'Wi-Fi')
        self.assertEqual(f.candidate_source_seq,50)
        self.assertEqual(f.candidate_time_us,2_000_000)
        self.assertEqual(f.inference_us,350)
        self.assertIsNone(parse_packet(model_packet(20,1),'USB'))

    def test_overlapping_automatic_150_row_windows_and_partial_tail(self):
        folder=Path(__file__).resolve().parent/'.test_output'/uuid.uuid4().hex
        s=Session(folder)
        for seq in range(210):
            pid=0 if seq<50 else 1 if seq<100 else 2
            s.ingest(parse_packet(model_packet(seq,pid),'Wi-Fi',host_ns=HOST+seq*20_000_000,utc_ns=HOST+seq*20_000_000))
        self.assertEqual(s.snapshot()['automatic_groups'],1)
        self.assertEqual(s.snapshot()['automatic_windows'],2)
        archive=s.export()
        with zipfile.ZipFile(archive) as z:
            records=json.loads(z.read('candidate_proposals.json'))
            self.assertEqual(len(records),2)
            self.assertTrue(all(r['valid'] and r['sample_count']==150 for r in records))
            self.assertEqual(records[0]['source_seq'],50)
            self.assertEqual(records[1]['source_seq'],100)
            for pid,start in [(1,0),(2,50)]:
                path=f'automatic_clips/{BOOT}_{pid:06d}.csv'
                import io
                rows=list(csv.DictReader(io.StringIO(z.read(path).decode())))
                self.assertEqual(int(rows[0]['seq']),start)
                self.assertEqual(int(rows[-1]['seq']),start+149)
            self.assertTrue(json.loads(z.read('session.json'))['model_telemetry_seen'])
            self.assertTrue(json.loads(z.read('session.json'))['expected_v2_firmware_observed'])
            groups=json.loads(z.read('automatic_activity_groups.json'))
            self.assertEqual(len(groups),1)
            self.assertEqual(groups[0]['window_ids'],[1,2])

    def test_incomplete_window_never_silently_valid(self):
        folder=Path(__file__).resolve().parent/'.test_output'/uuid.uuid4().hex
        s=Session(folder)
        for seq in range(80):
            s.ingest(parse_packet(model_packet(seq,int(seq>=50)),'USB',host_ns=HOST+seq*20_000_000,utc_ns=HOST+seq*20_000_000))
        s.export()
        records=json.loads((s.folder/'candidate_proposals.json').read_text())
        self.assertFalse(records[0]['valid'])
        self.assertEqual(records[0]['sample_count'],80)


if __name__=='__main__':unittest.main(verbosity=2)
