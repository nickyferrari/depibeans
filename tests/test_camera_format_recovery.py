import threading,unittest,types
from contextlib import nullcontext
from unittest.mock import patch
from depibeans.live_view import camera_frames
class Feature:
    def __init__(self,name,value):self.name=name;self.value=value
    def get_name(self):return self.name
    def get(self):return self.value
    def set(self,v):self.value=v
class Camera:
    def __init__(self):
        self.features={n:Feature(n,v) for n,v in {'PixelFormat':'Mono8','TriggerMode':'On','GevSCPSPacketSize':9000,'StreamBytesPerSecond':10000000,'ExposureAuto':'Off','ExposureMode':'Timed','GainAuto':'Off','Gain':0,'ExposureTimeAbs':15000,'Width':1936,'Height':1456}.items()}
        self.fail=False
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def get_serial(self):return 'test'
    def get_all_features(self):return list(self.features.values())
    def get_feature_by_name(self,n):return self.features[n]
    def get_frame_with_context(self,**kw):
        assert self.features['PixelFormat'].get()=='Mono12'
        if self.fail:raise RuntimeError('acquisition failed')
        return nullcontext(types.SimpleNamespace(get_status=lambda:'complete',as_numpy_ndarray=lambda:None,get_id=lambda:7))
class CameraFormatTests(unittest.TestCase):
    def run_camera(self,fail):
        camera=Camera();camera.fail=fail;before={k:f.get() for k,f in camera.features.items()};stop=threading.Event();frames=[]
        def publish(payload,frame_id,settings):frames.append(settings);stop.set()
        profile={'camera':{'serial':'test','transport_path':'fake'}}
        sdk=types.SimpleNamespace(get_all_cameras=lambda:[camera])
        with patch('depibeans.avt_camera.system',return_value=nullcontext(sdk)),patch.dict('sys.modules',{'vmbpy':types.SimpleNamespace(FrameStatus=types.SimpleNamespace(Complete='complete'))}),patch('depibeans.live_view.preview_png',return_value=b'png'):
            if fail:
                with self.assertRaisesRegex(RuntimeError,'acquisition failed'):camera_frames(profile,stop,publish)
            else:camera_frames(profile,stop,publish)
        self.assertEqual({k:f.get() for k,f in camera.features.items()},before)
        return frames
    def test_mono8_recovers_for_preview_and_restores_settings(self):self.assertEqual(self.run_camera(False)[0]['pixel_format'],'Mono12')
    def test_acquisition_failure_restores_format_and_trigger(self):self.assertEqual(self.run_camera(True),[])
