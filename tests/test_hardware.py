import ctypes as C
import unittest
from depibeans.hardware import LightingBoard,HardwareError,DeviceInfo
from depibeans.lighting import zone_packet,calibration_packet

class FakeNative:
    def __init__(self):self.commands=[];self.output=0x23;self.fail=None;self.closed=False;self.status_value=1
    def devices(self):return [{'name':'Nexys2','transport':65537}]
    def open(self,name,ptr):ptr._obj.value=10;return True
    def timeout(self,*args):return True
    def close(self,*args):self.closed=True;return True
    def detail(self):return 'test failure'
    def read(self,handle,register,ptr,overlap):ptr._obj.value=self.status_value;return True
    def send(self,handle,code,a,b,c,d,status,data):
        self.commands.append((code,a,b,c,d));status._obj.value=0xE0 if code==self.fail else 1
        data._obj.value=50000000 if code==2 else self.output if code==0x33 else 0
        return True

class HardwareTests(unittest.TestCase):
    def board(self):
        n=FakeNative();b=LightingBoard(n,'Nexys2',guard=lambda:None);b.connect();return b,n
    def test_handle_abi(self):self.assertEqual(C.sizeof(DeviceInfo),332)
    def test_connect_does_not_write_outputs(self):
        b,n=self.board();self.assertEqual([c[0] for c in n.commands],[2])
    def test_running_controller_rejected(self):
        n=FakeNative();n.status_value=15;b=LightingBoard(n,'Nexys2',guard=lambda:None)
        with self.assertRaises(HardwareError):b.connect()
        self.assertEqual(n.commands,[])
    def test_existing_java_blocks_open(self):
        def guard():raise HardwareError('Java running')
        n=FakeNative();b=LightingBoard(n,'Nexys2',guard=guard)
        with self.assertRaises(HardwareError):b.connect()
        self.assertEqual(b.handle.value,0)
    def test_exact_loop_structure_and_timing(self):
        b,n=self.board();n.commands=[]
        result=b.send_packet(zone_packet(2,1,1024))
        self.assertEqual(n.commands[0],(0x11,1,6,27,0))
        bits=[c for c in n.commands if c[0]==0x22]
        self.assertEqual(len(bits),114)
        self.assertEqual(bits[0],(0x22,1,0,3,50000))
        self.assertEqual(n.commands[-2],(0x31,1,35,0,0))
        self.assertEqual(n.commands[-1],(0x12,1,0,0,0))
        self.assertFalse(result['physical_output_verified'])
    def test_calibration_uses_small_loops(self):
        b,n=self.board();n.commands=[];b.send_packet(calibration_packet(1,0,[0,1,0]))
        self.assertEqual(n.commands[0],(0x11,1,17,27,0))
    def test_rejected_program_is_not_started_or_retried(self):
        b,n=self.board();n.commands=[];n.fail=0x22
        with self.assertRaises(HardwareError):b.send_packet(zone_packet(1,0,1))
        self.assertNotIn(0x12,[c[0] for c in n.commands]);count=len(n.commands)
        with self.assertRaises(HardwareError):b.send_packet(zone_packet(1,0,1))
        self.assertEqual(count,len(n.commands))
    def test_set_all_matches_three_legacy_zone_packets(self):
        b,n=self.board();packets=[];b.send_packet=lambda p:packets.append(p.wire_bytes)
        b.set_all_raw(32)
        self.assertEqual(packets,[bytes([0,z,0,32]) for z in range(3)])
        with self.assertRaises(ValueError):b.set_all_raw(4096)
    def test_unknown_board_name_rejected(self):
        n=FakeNative();b=LightingBoard(n,'Other',guard=lambda:None)
        with self.assertRaises(HardwareError):b.connect()
        self.assertFalse(b.handle.value)

if __name__=='__main__':unittest.main()
