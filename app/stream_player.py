"""Six-frame decoder with a cumulative presentation clock and live resizing.

The first frame is presented exactly once. Worker scheduling and the 16 ms GUI
timer do not add another rounding delay to every 41/42 ms source frame.
"""
import queue
import threading
import time
import zlib
from collections import OrderedDict
from pathlib import Path
from PIL import Image
from PySide6.QtGui import QImage,QPixmap
from loop_cache import DecodedLoopCache

class StreamPlayer:
    def __init__(self):
        self.stop=threading.Event();self.thread=None;self.frames=queue.Queue(6)
        self.first=OrderedDict();self.deadline=0;self.ended=False;self.error=None;self.path=None
        self.frame_index=0;self.playhead=0.;self.frame_start=0.;self.next_time=0.;self.last_clock=0.
        self.loop_cache=DecodedLoopCache();self.cache_loop=False
    @staticmethod
    def pixmap(raw,size):
        return QPixmap.fromImage(QImage(raw,size,size,size*4,QImage.Format.Format_RGBA8888).copy())
    def start(self,path,size,duration=4,start_frame=0,first_fraction=0.,cache_loop=False):
        self.close();self.path=Path(path);self.stop=threading.Event();self.frames=queue.Queue(6)
        self.size=size;self.duration=duration;self.ended=False;self.error=None
        self.cache_loop=cache_loop;loop_key=(str(path),size,self.path.stat().st_mtime_ns)
        cached=self.loop_cache.get(loop_key) if cache_loop else None
        key=loop_key+(start_frame,)
        if key not in self.first:
            if cached is not None:
                packed,delay,_=cached[start_frame];self.first[key]=(zlib.decompress(packed),delay)
            else:
                with Image.open(path) as src:
                    count=getattr(src,'n_frames',1);src.seek(start_frame);src.load()
                    im=src.convert('RGBA').resize((size,size),Image.Resampling.LANCZOS)
                    delay=float(src.info.get('duration',duration*1000/max(1,count)))/1000
                    self.first[key]=(im.tobytes(),max(.015,delay))
            while len(self.first)>20:self.first.popitem(last=False)
        self.first.move_to_end(key)
        raw,first_delay=self.first[key];first=self.pixmap(raw,size)
        first_fraction=max(0,min(.999,first_fraction))
        self.frame_index=start_frame;self.playhead=0.;self.frame_start=-first_delay*first_fraction
        self.next_time=first_delay*(1-first_fraction)
        self.last_clock=time.monotonic();self.deadline=self.last_clock+self.next_time
        stop,frames=self.stop,self.frames;first_raw=raw
        def emit(value):
            while not stop.is_set():
                try:frames.put(value,timeout=.05);return True
                except queue.Full:pass
            return False
        def decode():
            try:
                if cached is not None:
                    for packed,delay,i in cached[start_frame+1:]:
                        if stop.is_set():return
                        if not emit((zlib.decompress(packed),delay,i)):return
                else:
                    collect=cache_loop and start_frame==0 and self.loop_cache.begin(loop_key)
                    packed_frames=[];packed_size=0
                    if collect:
                        packed=zlib.compress(first_raw,1);packed_frames.append((packed,first_delay,0));packed_size=len(packed)
                        if packed_size>self.loop_cache.entry_limit:
                            self.loop_cache.skip(loop_key);packed_frames.clear();collect=False
                    with Image.open(path) as src:
                        count=getattr(src,'n_frames',1)
                        for i in range(start_frame+1,count):
                            if stop.is_set():return
                            src.seek(i)
                            raw=src.convert('RGBA').resize((size,size),Image.Resampling.LANCZOS).tobytes()
                            delay=max(.015,float(src.info.get('duration',duration*1000/max(1,count)))/1000)
                            if collect:
                                packed=zlib.compress(raw,1);packed_size+=len(packed)
                                if packed_size>self.loop_cache.entry_limit:
                                    self.loop_cache.skip(loop_key);packed_frames.clear();collect=False
                                else:packed_frames.append((packed,delay,i))
                            if not emit((raw,delay,i)):return
                    if collect and not stop.is_set():self.loop_cache.put(loop_key,packed_frames,packed_size)
                emit((None,0,None))
            except Exception as error:
                if not stop.is_set():
                    try:frames.put((None,0,type(error).__name__),timeout=.2)
                    except queue.Full:pass
        self.thread=threading.Thread(target=decode,name='pet-frame-reader',daemon=True);self.thread.start()
        return first
    def advance(self,size,speed=1):
        if self.ended:return None,False
        now=time.monotonic();speed=max(.25,min(3.,speed))
        self.playhead+=max(0,now-self.last_clock)*speed;self.last_clock=now;latest=None;ended=False
        while self.playhead+1e-8>=self.next_time:
            try:raw,delay,index=self.frames.get_nowait()
            except queue.Empty:break
            if raw is None:
                self.ended=True;self.error=index;ended=True;break
            self.frame_start=self.next_time;self.next_time+=delay;self.frame_index=index;latest=raw
        self.deadline=now+max(0,self.next_time-self.playhead)/speed
        return (self.pixmap(latest,self.size) if latest is not None else None),ended
    def resize(self,size):
        """Reopen at the current source frame, preserving its remaining time."""
        if size==self.size or self.path is None:return None
        fraction=(self.playhead-self.frame_start)/max(.001,self.next_time-self.frame_start)
        return self.start(self.path,size,self.duration,self.frame_index,fraction,cache_loop=self.cache_loop)
    def close(self):
        self.stop.set()
        if self.thread and self.thread.is_alive():self.thread.join(.3)
        self.thread=None
