"""Render an AVT Mono12 TIFF for display; preserve the original scientific TIFF."""
import struct
import zlib

def mono12_png(path,display_max=4095,display_min=0,masked=False,color=False):
    import numpy as np
    import tifffile
    frame=tifffile.imread(path).squeeze()
    if frame.ndim!=2 or frame.dtype.kind not in 'uif' or frame.size>20000000:
        raise ValueError('Unsupported preview frame')
    valid=np.isfinite(frame)
    if (not masked and not valid.all()) or not np.isfinite(display_max) or not np.isfinite(display_min) or display_max<=display_min:raise ValueError('Invalid display range')
    normalized=np.clip((np.where(valid,frame,display_min).astype(np.float64)-display_min)/(display_max-display_min),0,1)
    if color:
        stops=np.array([[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]])
        pixels=np.stack([np.interp(normalized,np.linspace(0,1,5),stops[:,i]) for i in range(3)],axis=-1).astype('uint8')
        pixels[~valid]=0
    else:pixels=(normalized*255).astype('uint8')
    h,w=pixels.shape[:2]
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\0'+row.tobytes() for row in pixels)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2 if color else 0,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
