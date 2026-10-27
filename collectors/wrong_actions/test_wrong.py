import csv,io,json,time,unittest,zipfile
from pathlib import Path
import numpy as np
from wrong_core import Session, MISTAKES
from collector_core import parse_packet
from test_collector import TempFixture, frame, packet, HOST


class WrongTests(unittest.TestCase):
    def setUp(self):
        self.fixture=TempFixture();self.s=Session(self.fixture.name)

    def tearDown(self):self.s.close_input()

    def feed(self,a,b):
        for i in range(a,b):self.s.ingest(frame(i))

    def test_variable_length_negative_export_and_other_valid_class(self):
        self.feed(0,10)
        self.s.start('gesture','sit',HOST+190_000_000,mistake_id='point_up',mistake_description='Point up')
        self.feed(10,30);first=self.s.finish(HOST+590_000_000)
        self.assertTrue(first['accepted']);self.assertEqual(first['kind'],'incorrect_attempt')
        self.assertFalse(first['is_correct_for_intended']);self.assertIsNone(first['global_class_label'])
        self.s.start('gesture','sit',HOST+595_000_000,mistake_id='other',observed_valid_gesture='paw')
        self.feed(30,60);second=self.s.finish(HOST+1_190_000_000)
        self.assertTrue(second['accepted']);self.assertEqual(second['global_class_label'],'paw')
        archive=self.s.export()
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip());names=z.namelist()
            self.assertFalse(any(n.startswith('gesture_clips/') for n in names))
            clips=[n for n in names if n.startswith('wrong_examples/sit/') and n.endswith('.csv')]
            self.assertEqual(len(clips),2)
            counts=[]
            for p in clips:
                rows=list(csv.DictReader(io.StringIO(z.read(p).decode())));counts.append(len(rows))
                self.assertEqual(list(rows[0]),['ax','ay','az','gx','gy','gz','thumb','index','middle'])
                self.assertTrue(all(r['thumb'] in ('0.0','1.0') for r in rows))
            self.assertEqual(sorted(counts),[20,30])
            data=np.load(io.BytesIO(z.read('wrong_examples.npz')),allow_pickle=False)
            np.testing.assert_array_equal(data['row_splits'],[0,20,50])
            self.assertEqual(data['values'].shape,(50,9))
            self.assertEqual(data['labels'].tolist(),['wrong_sit','wrong_sit'])
            meta=json.loads(z.read('session.json'));self.assertEqual(meta['accepted_wrong_counts']['sit'],2)

    def test_no_count_cap_and_no_false_global_background(self):
        # More than 40 takes are accepted without auto-advancing or imposing a quota.
        self.feed(0,10)
        seq=10
        for take in range(45):
            start=HOST+(seq-1)*20_000_000+10_000_000
            self.s.start('incorrect_attempt','come',start)
            self.feed(seq,seq+15);seq+=15
            e=self.s.finish(HOST+(seq-1)*20_000_000+10_000_000)
            self.assertTrue(e['accepted']);self.assertIsNone(e['global_class_label'])
        self.assertEqual(self.s.snapshot()['counts']['come'],45)

    def test_fault_does_not_count_and_cancel_keeps_raw(self):
        self.feed(0,10);self.s.start('gesture','sit',HOST+190_000_000)
        self.feed(10,20);bad=frame(20);bad.rails=4;self.s.ingest(bad)
        self.feed(21,35);e=self.s.finish(HOST+690_000_000)
        self.assertFalse(e['accepted']);self.assertEqual(self.s.snapshot()['counts']['sit'],0)
        self.assertEqual(len(self.s.frames),35)

    def test_current_detector_packet_compatible_without_model_gating(self):
        base=packet(70).decode().strip().replace('MILO1,','MILO3,',1)
        f=parse_packet((base+',0.999,2,2000000,50,1,500\n').encode(),'Wi-Fi')
        self.assertIsNotNone(f);self.assertEqual(f.features[6:],(0,1,0))
        base=base.replace('MILO3,','MILO2,',1)
        self.assertIsNotNone(parse_packet((base+',0.000,0,0,0,0,0\n').encode(),'USB'))

    def test_same_gesture_cannot_be_labelled_correct_and_wrong(self):
        self.feed(0,10)
        with self.assertRaises(ValueError):self.s.start('gesture','sit',HOST+190_000_000,observed_valid_gesture='sit')


if __name__=='__main__':unittest.main(verbosity=2)
