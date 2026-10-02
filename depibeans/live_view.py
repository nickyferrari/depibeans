"""Ephemeral camera preview. One in-memory frame, no frame files or FPGA access."""
import threading
import time
import struct
import zlib


def preview_png(pixels):
    import numpy as np
    pixels=pixels.squeeze()
    if pixels.ndim!=2 or pixels.dtype.kind!='u' or pixels.dtype.itemsize!=2:
        raise ValueError('Expected Mono12 in uint16 storage')
    # Display derivative only; fixed sensor scale, half-resolution preview.
    image=(np.clip(pixels[::2,::2],0,4095).astype('uint32')*255//4095).astype('uint8')
    h,w=image.shape
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\0'+row.tobytes() for row in image)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(raw,1))+chunk(b'IEND',b'')


def camera_frames(profile,stop,publish):
    from .avt_camera import system
    from vmbpy import FrameStatus
    c=profile['camera'];preview=profile.get('live_preview',{'exposure_us':250,'gain':12})
    with system(c['transport_path']) as sdk:
        cameras=[camera for camera in sdk.get_all_cameras() if camera.get_serial()==c['serial']]
        if len(cameras)!=1:raise RuntimeError('Configured camera was not uniquely found')
        with cameras[0] as camera:
            names={f.get_name() for f in camera.get_all_features()}
            exposure='ExposureTimeAbs' if 'ExposureTimeAbs' in names else 'ExposureTime'
            settings=[('TriggerMode','Off'),('PixelFormat','Mono12'),('GevSCPSPacketSize',1500),('StreamBytesPerSecond',5000000),
                      ('ExposureAuto','Off'),('ExposureMode','Timed'),('GainAuto','Off'),('Gain',preview['gain']),
                      (exposure,preview['exposure_us'])]
            # Restore the verified preview format for this session; preserve ROI/binning.
            # Original settings are restored on success, cancellation, and acquisition failure.
            originals={n:camera.get_feature_by_name(n).get() for n,v in settings}
            changed=[]
            try:
                for n,v in settings:
                    camera.get_feature_by_name(n).set(v);changed.append(n)
                if str(camera.get_feature_by_name('PixelFormat').get())!='Mono12':
                    raise RuntimeError('Camera did not accept Mono12 preview format')
                readback={'exposure_us':camera.get_feature_by_name(exposure).get(),'gain':camera.get_feature_by_name('Gain').get(),'width':camera.get_feature_by_name('Width').get(),'height':camera.get_feature_by_name('Height').get(),'pixel_format':'Mono12'}
                while not stop.is_set():
                    started=time.monotonic()
                    with camera.get_frame_with_context(timeout_ms=4000) as frame:
                        if frame.get_status()!=FrameStatus.Complete:raise RuntimeError('Incomplete live frame')
                        payload=preview_png(frame.as_numpy_ndarray())
                        frame_id=frame.get_id()
                    if stop.is_set():break
                    publish(payload,frame_id,readback)
                    stop.wait(max(0,1.0-(time.monotonic()-started)))
            finally:
                errors=[]
                # TriggerMode was changed first and is restored last.
                for n in reversed(changed):
                    try:camera.get_feature_by_name(n).set(originals[n])
                    except Exception as exc:errors.append(n+': '+str(exc))
                if errors:raise RuntimeError('Camera restore failed: '+'; '.join(errors))


class LiveView:
    def __init__(self,job_lock,source=camera_frames,idle_seconds=15,max_seconds=900):
        self.job_lock=job_lock;self.source=source;self.idle_seconds=idle_seconds;self.max_seconds=max_seconds
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None
        self.running=False;self.error=None;self.payload=None;self.created=None;self.frame_id=None;self.sequence=0
        self.readback=None;self.last_seen=0;self.started=0;self.session=None

    def start(self,profile,request_id):
        if not isinstance(request_id,str) or not 1<=len(request_id)<=128:raise ValueError('Request ID required')
        with self.lock:
            if self.running:
                # An explicit second viewer may join, but never starts a second camera owner.
                self.last_seen=time.monotonic();return self.status()
            if self.error and self.error.startswith('Camera restore failed:'):
                raise ValueError('Camera restoration needs maintenance before restarting live view')
            if not self.job_lock.acquire(blocking=False):raise ValueError('Wait for the active operation to finish')
            self.running=True;self.error=None;self.payload=None;self.created=None;self.frame_id=None;self.sequence=0
            self.readback=None;self.session=request_id;self.started=self.last_seen=time.monotonic();self.stop_event.clear()
            self.thread=threading.Thread(target=self._run,args=(profile,),daemon=True)
            self.thread.start()
            return self.status()

    def _run(self,profile):
        def watchdog():
            while not self.stop_event.wait(.25):
                with self.lock:
                    now=time.monotonic()
                    if now-self.last_seen>self.idle_seconds or now-self.started>self.max_seconds:
                        self.stop_event.set()
        watcher=threading.Thread(target=watchdog,daemon=True);watcher.start()
        try:self.source(profile,self.stop_event,self.publish)
        except Exception as exc:
            with self.lock:self.error=str(exc)
        finally:
            self.stop_event.set();watcher.join(timeout=1)
            with self.lock:self.running=False;self.payload=None;self.created=None;self.frame_id=None
            self.job_lock.release()

    def publish(self,payload,frame_id,readback=None):
        with self.lock:
            self.readback=readback;self.payload=payload;self.frame_id=frame_id;self.sequence+=1;self.created=time.time()

    def frame(self):
        with self.lock:
            if not self.running:raise ValueError(self.error or 'Live view is stopped')
            self.last_seen=time.monotonic()
            if self.payload is None:raise ValueError('Waiting for first live frame')
            if time.time()-self.created>6:raise ValueError('Live camera frame is stale')
            return self.payload,self.created,self.sequence

    def stop(self):
        self.stop_event.set()
        thread=self.thread
        if thread:thread.join(timeout=8)
        if thread and thread.is_alive():raise ValueError('Camera is still stopping; try again after cleanup')
        return self.status()

    def status(self):
        with self.lock:return {'running':self.running,'error':self.error,'created':self.created,
             'settings':self.readback,'sequence':self.sequence,'frame_id':self.frame_id,'recording':False,'max_seconds':self.max_seconds}
