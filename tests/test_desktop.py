import os
import tempfile
import time
import unittest
from pathlib import Path

@unittest.skipUnless(os.name=='nt','Windows desktop checks')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from depibeans.desktop import Desktop
        self.temp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw()
        self.app=Desktop(self.root,Path(self.temp.name))
    def tearDown(self):
        self.app.board=None;self.app.close();self.temp.cleanup()
    def test_construction_does_not_open_hardware(self):
        self.assertIsNone(self.app.board);self.assertEqual(len(self.app.raw),48)
        self.assertEqual(self.app.db.execute('SELECT count(*) FROM actions').fetchone()[0],0)
    def test_dispatch_uses_submitted_value_and_records_completion(self):
        class FakeBoard:
            def send_packet(self,p):self.packet=p;return {'fpga_completed':True}
        fake=FakeBoard();self.app.board=fake
        self.app.raw[1,0].set('123');self.app.apply_zone(1,0)
        self.app.raw[1,0].set('999')
        deadline=time.monotonic()+3
        while self.app.future and time.monotonic()<deadline:self.root.update();time.sleep(.02)
        self.assertIsNone(self.app.future)
        self.assertEqual(fake.packet.wire_bytes,bytes([2,0,0,123]))
        self.assertEqual(self.app.sent_raw[1,0],123)
        self.assertEqual(self.app.db.execute('SELECT state FROM actions').fetchone()[0],'completed')
    def test_raw_value_out_of_range_rejected_before_dispatch(self):
        self.app.raw[1,0].set('4096')
        with self.assertRaises(ValueError):self.app.apply_zone(1,0)
        self.assertIsNone(self.app.future)
