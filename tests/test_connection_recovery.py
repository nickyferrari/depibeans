import unittest
from unittest.mock import patch
from depibeans.chamber_fpga import ChamberFPGA
from depibeans.hardware import LightingBoard, HardwareError
from tests.test_hardware import FakeNative

class RecoveryNative(FakeNative):
    def __init__(self, status=0, acknowledge=True):
        super().__init__(); self.status_value=status; self.acknowledge=acknowledge
    def send(self,handle,code,a,b,c,d,status,data):
        super().send(handle,code,a,b,c,d,status,data)
        if code==9:
            if self.acknowledge:self.status_value=9
            status._obj.value=self.status_value
        return True

class ConnectionRecoveryTests(unittest.TestCase):
    def boards(self,n):
        return [LightingBoard(n,'Nexys2',guard=lambda:None),ChamberFPGA('Nexys2',native=n)]
    def test_cold_connection_pings_once_then_checks_clock_without_outputs(self):
        for kind in (LightingBoard,ChamberFPGA):
            n=RecoveryNative();b=self.boards(n)[kind is ChamberFPGA]
            with patch('depibeans.chamber_fpga.no_linux_java_controller'):
                b.connect()
            self.assertEqual([c[0] for c in n.commands],[9,2])
            self.assertEqual(b.status(),9)
    def test_running_and_error_states_never_ping_or_clear(self):
        for status in (15,238,224,127):
            for index in (0,1):
                n=RecoveryNative(status);b=self.boards(n)[index]
                with patch('depibeans.chamber_fpga.no_linux_java_controller'):
                    with self.assertRaises(HardwareError):b.connect()
                self.assertEqual(n.commands,[]);self.assertTrue(n.closed)
    def test_no_retry_on_failed_ping(self):
        for index in (0,1):
            n=RecoveryNative(acknowledge=False);b=self.boards(n)[index]
            with patch('depibeans.chamber_fpga.no_linux_java_controller'):
                with self.assertRaises(HardwareError):b.connect()
            self.assertEqual([c[0] for c in n.commands],[9]);self.assertTrue(n.closed)
    def test_zero_mid_session_is_not_auto_recovered(self):
        n=RecoveryNative(1);b=self.boards(n)[1]
        with patch('depibeans.chamber_fpga.no_linux_java_controller'):b.connect()
        n.status_value=0
        with self.assertRaises(HardwareError):b.require_idle()
        self.assertEqual([c[0] for c in n.commands],[2])
