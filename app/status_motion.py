"""Small vector glyphs sharing three capsule/ring parts and one motion clock."""
import math
from typing import NamedTuple

BUSY_RING_RADIUS=1.9
BUSY_RING_STROKE=1.25
BUSY_BREATH_SECONDS=2.0
BUSY_ROTATION_SECONDS=3.0
MORPH_SECONDS=.48


class Part(NamedTuple):
    x:float
    y:float
    length:float=0.       # Half the straight segment of a vertical capsule.
    radius:float=1.
    hole:float=0.         # Inner capsule radius; zero means a solid shape.
    angle:float=0.        # Degrees, about the part's own center.
    opacity:float=1.


def busy_ring_centers(elapsed):
    breath=(1-math.cos(math.tau*elapsed/BUSY_BREATH_SECONDS))*.5
    radius=3.+1.8*breath
    angle=-math.pi/2+math.tau*elapsed/BUSY_ROTATION_SECONDS
    return tuple((8+radius*math.cos(angle+i*math.tau/3),
                  8+radius*math.sin(angle+i*math.tau/3)) for i in range(3))


def rotate_parts(parts,angle):
    radians=math.radians(angle);c,s=math.cos(radians),math.sin(radians)
    return tuple(p._replace(x=8+(p.x-8)*c-(p.y-8)*s,
                            y=8+(p.x-8)*s+(p.y-8)*c,angle=p.angle+angle) for p in parts)


class GlyphMotion:
    """Retarget from the current geometry, including its incoming velocity."""
    def __init__(self,now=0.):
        self.state='idle';self.since=now;self.started=None
        self.source=None;self.velocity=None;self.attention_at=None

    def shaking(self,now):
        return self.state=='attention' and self.attention_at is not None and 0<=now-self.attention_at<1.2

    def moving(self,now):
        return (self.started is not None and now-self.started<MORPH_SECONDS
                or self.state in ('busy','waiting') or self.shaking(now))

    def steady(self,now):
        elapsed=max(0.,now-self.since)
        if self.state=='busy':
            return tuple(Part(x,y,radius=BUSY_RING_RADIUS+BUSY_RING_STROKE/2,
                              hole=BUSY_RING_RADIUS-BUSY_RING_STROKE/2)
                         for x,y in busy_ring_centers(elapsed))
        if self.state=='waiting':
            radius=1.35+.15*math.sin(math.tau*elapsed/BUSY_BREATH_SECONDS)
            return tuple(Part(x,8,radius=radius) for x in (3.5,8,12.5))
        if self.state=='paused':
            return (Part(5.6,8,2.8,1.05),Part(10.4,8,2.8,1.05),Part(8,8,opacity=0))
        if self.state in ('attention','warning'):
            parts=(Part(8,5.6,.9,1),Part(8,7.4,.9,1),Part(8,12,radius=1.15))
            if self.shaking(now):
                # Two gentle oscillations, both starting and ending at rest.
                t=(now-self.attention_at)/1.2
                parts=rotate_parts(parts,9*math.sin(math.tau*2*t)*math.sin(math.pi*t)**2)
            return parts
        if self.state=='complete':
            return (Part(5.75,9.25,math.sqrt(2.5**2*2)/2,.95,angle=-45),
                    Part(9.4,7.9,math.hypot(4.8,5.2)/2,.95,angle=math.degrees(math.atan2(4.8,5.2))),
                    Part(7,10.5,radius=.95,opacity=0))
        return (Part(8,8,radius=1.8),Part(8,8,opacity=0),Part(8,8,opacity=0))

    def sample(self,now):
        target=self.steady(now)
        if self.started is None or now-self.started>=MORPH_SECONDS:return target
        t=max(0.,(now-self.started)/MORPH_SECONDS)
        ease=t*t*(3-2*t)
        # Hermite's initial tangent carries rotation into the gathering motion.
        coast=MORPH_SECONDS*t*(1-t)**2
        parts=[]
        for start,end,velocity in zip(self.source,target,self.velocity):
            values=[a+(b-a)*ease+v*coast for a,b,v in zip(start,end,velocity)]
            x,y,length,radius,hole,angle,opacity=values
            length=max(0.,length);radius=max(.05,radius)
            hole=max(0.,min(radius,hole));opacity=max(0.,min(1.,opacity))
            # Keep every intermediate silhouette inside the fixed 16px canvas.
            radians=math.radians(angle)
            rx=abs(math.sin(radians))*length+radius
            ry=abs(math.cos(radians))*length+radius
            x=max(.4+rx,min(15.6-rx,x));y=max(.4+ry,min(15.6-ry,y))
            parts.append(Part(x,y,length,radius,hole,angle,opacity))
        return tuple(parts)

    def set_state(self,state,now,animate=True):
        if state==self.state:return False
        source=self.sample(now)
        previous=self.sample(now-.002)
        self.velocity=tuple(tuple((a-b)/.002 for a,b in zip(p,q)) for p,q in zip(source,previous))
        self.source=source;self.state=state;self.since=now
        self.started=now if animate else None
        self.attention_at=now+MORPH_SECONDS if state=='attention' and animate else None
        return True

    def settle(self):
        self.started=None;self.attention_at=None

    def notify_again(self,now):
        if self.state=='attention' and not self.shaking(now):
            self.attention_at=max(now,self.started+MORPH_SECONDS) if self.started is not None else now
