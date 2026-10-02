import sys,threading,time,unittest
from depibeans.live_view import LiveView
class Tests(unittest.TestCase):
 def test_single_owner_expiry_and_memory_clear(self):
  lock=threading.Lock();calls=[]
  def source(p,stop,publish):
   calls.append(1);publish(b'png',5);stop.wait(2)
  live=LiveView(lock,source,idle_seconds=.1,max_seconds=1)
  live.start({},'a');time.sleep(.03);live.start({},'b')
  self.assertEqual(live.frame()[0],b'png');self.assertEqual(len(calls),1);self.assertFalse(lock.acquire(False))
  time.sleep(.4);self.assertFalse(live.status()['running']);self.assertIsNone(live.payload);self.assertTrue(lock.acquire(False));lock.release()
 def test_failure_releases_lock(self):
  lock=threading.Lock()
  def source(*a):raise RuntimeError('camera unavailable')
  live=LiveView(lock,source);live.start({},'a');time.sleep(.05)
  self.assertEqual(live.status()['error'],'camera unavailable');self.assertTrue(lock.acquire(False));lock.release()
 def test_existing_job_blocks_start(self):
  lock=threading.Lock();lock.acquire();live=LiveView(lock)
  with self.assertRaises(ValueError):live.start({},'a')
  lock.release()
 def test_read_does_not_start_camera_and_stop_clears_frame(self):
  calls=[]
  def source(p,stop,publish):calls.append(1);publish(b'frame',1);stop.wait(2)
  live=LiveView(threading.Lock(),source)
  with self.assertRaises(ValueError):live.frame()
  self.assertEqual(calls,[])
  live.start({},'id');time.sleep(.02);live.stop()
  self.assertIsNone(live.payload);self.assertFalse(live.status()['running'])
 def test_hard_deadline_even_with_viewer(self):
  def source(p,stop,publish):publish(b'frame',1);stop.wait(2)
  live=LiveView(threading.Lock(),source,idle_seconds=10,max_seconds=.1)
  live.start({},'id');time.sleep(.02);live.frame();time.sleep(.3)
  self.assertFalse(live.status()['running'])
if __name__=='__main__':unittest.main()
