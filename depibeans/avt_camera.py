"""AVT Linux acquisition adapter. Discovery never acquires images.

Capture is an explicit commissioned operation; vendor API imports are lazy.
The two-second legacy preparation allowance is retained until measured readiness
can replace it. No automatic trigger retry is performed.
"""
from pathlib import Path
import json
import queue
import threading
import time


def system(transport_path):
    from vmbpy import VmbSystem
    return VmbSystem.get_instance().set_path_configuration(str(transport_path))


def discover(transport_path):
    with system(transport_path) as sdk:
        return {'version':sdk.get_version(),
                'transports':[{'name':t.get_name(),'path':t.get_path()} for t in sdk.get_all_transport_layers()],
                'cameras':[{'id':c.get_id(),'model':c.get_model(),'serial':c.get_serial()} for c in sdk.get_all_cameras()]}


def _capture(*,transport_path,serial,frames,exposure_us,destination,trigger,
            protocol_duration_s,width=1936,height=1456,packet_size=8999,
            commissioning_authorized=False, stream_bytes_per_second=None, gain=None):
    if commissioning_authorized is not True:raise RuntimeError('Camera has not been commissioned')
    if type(frames) is not int or not 1<=frames<=10000:raise ValueError('Invalid frame count')
    if not 0<exposure_us<=1_000_000 or not 0<=protocol_duration_s<=3600:raise ValueError('Invalid capture timing')
    from vmbpy import FrameStatus,PixelFormat
    import tifffile
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=False)
    metadata={'serial':serial,'expected_frames':frames,'state':'preparing','frames':[],
              'pixel_format':'Mono12','storage_bits':16,'sample_bits':12}
    def save_metadata():
        tmp=dest/'metadata.tmp';tmp.write_text(json.dumps(metadata,indent=2));tmp.replace(dest/'metadata.json')
    save_metadata();q=queue.Queue(maxsize=8);faults=[];done=threading.Event();received=[0];previous=[None]
    def writer():
        try:
            while True:
                item=q.get()
                if item is None:break
                sequence,frame_id,image=item
                path=dest/f'frame-{sequence:06d}.tif'
                tifffile.imwrite(path,image,photometric='minisblack')
                metadata['frames'].append({'sequence':sequence,'camera_frame_id':frame_id,'file':path.name,'shape':list(image.shape),'dtype':str(image.dtype)})
        except Exception as exc:faults.append(str(exc));done.set()
    thread=threading.Thread(target=writer,daemon=True)
    thread.start()
    try:
        with system(transport_path) as sdk:
            matches=[c for c in sdk.get_all_cameras() if c.get_serial()==serial]
            if len(matches)!=1:raise RuntimeError('Configured camera was not uniquely found')
            with matches[0] as camera:
                metadata['model']=camera.get_model();metadata['camera_id']=camera.get_id()
                settings=[('TriggerMode','Off'),('PixelFormat','Mono12'),('BinningHorizontal',1),('BinningVertical',1),
                          ('Width',width),('Height',height),('GevSCPSPacketSize',packet_size),('Gamma',1.0),
                          ('ExposureAuto','Off'),('ExposureMode','Timed'),('GainAuto','Off'),
                          ('TriggerSelector','FrameStart'),('TriggerSource','Line1'),('TriggerActivation','LevelHigh')]
                if stream_bytes_per_second is not None:settings.append(('StreamBytesPerSecond',stream_bytes_per_second))
                if gain is not None:settings.append(('Gain',gain))
                names={f.get_name() for f in camera.get_all_features()}
                exposure_name='ExposureTimeAbs' if 'ExposureTimeAbs' in names else 'ExposureTime'
                settings.extend([(exposure_name,exposure_us),('TriggerMode','On')])
                missing=[n for n,v in settings if n not in names]
                if missing:raise RuntimeError('Required camera features missing: '+', '.join(missing))
                originals={n:camera.get_feature_by_name(n).get() for n,v in settings}
                changed=[]
                try:
                    for name,value in settings:
                        camera.get_feature_by_name(name).set(value);changed.append(name)
                    metadata['feature_readback']={name:str(camera.get_feature_by_name(name).get()) for name,value in settings}
                    def callback(cam,stream,frame):
                        try:
                            if frame.get_status()!=FrameStatus.Complete:raise RuntimeError('Incomplete camera frame')
                            frame_id=frame.get_id()
                            if previous[0] is not None and frame_id!=previous[0]+1:raise RuntimeError('Camera frame gap or duplicate')
                            previous[0]=frame_id
                            if received[0]>=frames:raise RuntimeError('Unexpected extra camera frame')
                            image=frame.as_numpy_ndarray().copy()
                            if image.dtype.kind!='u' or image.dtype.itemsize!=2:raise RuntimeError('Expected unsigned 16-bit camera storage')
                            if image.max()>4095:raise RuntimeError('Camera samples exceed Mono12 range')
                            if image.shape[:2]!=(height,width):raise RuntimeError('Unexpected image dimensions')
                            q.put_nowait((received[0],frame_id,image));received[0]+=1
                            if received[0]==frames:done.set()
                        except Exception as exc:faults.append(str(exc));done.set()
                        finally:cam.queue_frame(frame)
                    camera.start_streaming(handler=callback,buffer_count=8)
                    try:
                        time.sleep(2)
                        metadata['state']='armed';save_metadata()
                        trigger()
                        if not done.wait(protocol_duration_s+10):raise TimeoutError('Camera frame completion timed out')
                        if faults:raise RuntimeError('; '.join(faults))
                    finally:camera.stop_streaming()
                finally:
                    # Restore feature settings after closing the acquisition stream.
                    if changed:
                        try:camera.get_feature_by_name('TriggerMode').set('Off')
                        except Exception as exc:faults.append('Disable trigger during restore: '+str(exc))
                    for name in reversed(list(dict.fromkeys(changed))):
                        try:camera.get_feature_by_name(name).set(originals[name])
                        except Exception as exc:faults.append('Restore '+name+': '+str(exc))
        q.put(None,timeout=10);thread.join(timeout=30)
        if thread.is_alive() or faults or len(metadata['frames'])!=frames:raise RuntimeError('Image persistence or camera cleanup incomplete: '+'; '.join(faults))
        metadata['state']='completed';save_metadata();return metadata
    except BaseException as exc:
        metadata['state']='failed';metadata['error']=str(exc)
        try:q.put_nowait(None)
        except queue.Full:pass
        thread.join(timeout=5)
        cleanup_errors=[e for e in faults if e.startswith(('Restore ','Disable trigger'))]
        if cleanup_errors:metadata['cleanup_errors']=cleanup_errors
        save_metadata()
        if cleanup_errors:raise RuntimeError('Camera restoration failed: '+'; '.join(cleanup_errors)) from exc
        raise


def capture(*, stream_bytes_per_second=None, gain=None, protocol_fields=None, **kwargs):
    """Apply preview analog/transport settings before the acquisition session.

    Matches the physically verified standalone capture path. Restore originals
    even after an acquisition error; do not replay the trigger on failure.
    """
    if kwargs.get('commissioning_authorized') is not True:
        raise RuntimeError('Camera has not been commissioned')
    transport=kwargs['transport_path'];serial=kwargs['serial'];originals=[];readback={}
    def set_feature(name,value):
        with system(transport) as sdk:
            matches=[c for c in sdk.get_all_cameras() if c.get_serial()==serial]
            if len(matches)!=1:raise RuntimeError('Configured camera was not uniquely found')
            with matches[0] as camera:
                feature=camera.get_feature_by_name(name);old=feature.get();feature.set(value)
                return old,feature.get()
    try:
        for name,value in [('StreamBytesPerSecond',stream_bytes_per_second),('Gain',gain)]:
            if value is not None:
                old,actual=set_feature(name,value);originals.append((name,old));readback[name]=str(actual)
        result=_capture(**kwargs)
        result['preview_feature_readback']=readback
        path=Path(kwargs['destination'])/'metadata.json'
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2));temp.replace(path)
        if protocol_fields is not None:
            try:
                from .measurement_images import average_capture
                result['averages']=average_capture(kwargs['destination'],protocol_fields)
            except Exception as exc:
                result['average_error']=str(exc)
                temp.write_text(json.dumps(result,indent=2));temp.replace(path)
        return result
    finally:
        errors=[]
        for name,value in reversed(originals):
            try:set_feature(name,value)
            except Exception as exc:errors.append(name+': '+str(exc))
        if errors:raise RuntimeError('Camera settings restoration failed: '+'; '.join(errors))
