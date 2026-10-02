"""Phase-specific arithmetic means; source images remain unchanged."""
import json
from pathlib import Path
from .camera_protocol import expand,flag

def average_capture(destination,fields):
    import numpy as np
    import tifffile
    root=Path(destination).resolve();path=root/'metadata.json'
    meta=json.loads(path.read_text())
    if meta.get('state')!='completed':raise ValueError('Only completed captures can be averaged')
    loops=int(fields['NumberLoops']);counts=expand(fields,'FramesPerLoop',loops,int)
    sat=expand(fields,'SaturationFlash',loops,flag);lights=expand(fields,'MeasuringLight',loops,int)
    frames=meta['frames']
    if sum(counts)!=len(frames):raise ValueError('Frame count does not match pulse phases')
    offset=0;means=[]
    for phase,count in enumerate(counts):
        group=frames[offset:offset+count];offset+=count
        if count<2:continue
        total=None;clipped=0
        for frame in group:
            file=(root/frame['file']).resolve()
            if not file.is_relative_to(root):raise ValueError('Frame outside capture')
            image=tifffile.imread(file).squeeze()
            if image.ndim!=2 or not np.isfinite(image).all():raise ValueError('Invalid image')
            if total is None:total=np.zeros(image.shape,dtype=np.float64)
            if total.shape!=image.shape:raise ValueError('Image dimensions changed')
            total+=image;clipped+=int(np.count_nonzero(image>=4095))
        mean=(total/count).astype(np.float32);name=f'mean-phase-{phase+1:03d}.tif'
        tifffile.imwrite(root/name,mean,photometric='minisblack',description='Arithmetic mean in raw camera units; no background subtraction')
        means.append({'file':name,'kind':'mean','phase':phase+1,'frame_count':count,'source_frames':[f['file'] for f in group],
          'label':('Saturation' if sat[phase] else 'Measuring' if lights[phase] else 'Background')+' mean',
          'saturation':sat[phase],'measuring_channel':lights[phase], 'display_max':max(1,float(mean.max())),
          'clipped_fraction':clipped/(count*mean.size),'method':'arithmetic mean; float32 raw camera units'})
    meta['averages']=means;meta['protocol_fields']=fields
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(meta,indent=2));temp.replace(path)
    return means
