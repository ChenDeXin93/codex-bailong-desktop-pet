"""Sample only the newest public activity at safe animation boundaries.

No network, model calls, hidden reasoning, tool arguments or FIFO of old states.
Observers replace snapshots cheaply; semantic classification runs only on poll.
"""
from collections import OrderedDict,deque
from dataclasses import dataclass
import re

ACTIVE={'thinking','working','responding'}

@dataclass(frozen=True)
class Reaction:
    kind:str
    action_id:str
    session:str=''
    turn:str=''

def classify(event):
    state=event.get('state','idle');activity=event.get('activity','')
    if state in ('idle','offline','complete'):return None
    if state=='interrupted':return Reaction('paused','idle2')
    # Explicit lifecycle state wins over incidental words such as "completed"
    # in commentary or a final answer. Celebration needs a completion event.
    if state=='responding':return Reaction('reply','01')
    if state=='thinking':return Reaction('thinking','quota')
    if state!='working':return None
    if activity in ('research','read','verify','retry','compact'):return Reaction('review','quota')
    if activity in ('edit','execute','create'):return Reaction('working','22')
    text=str(event.get('text',''))[:1000].lower()
    if re.search(r'失败|报错|未通过|暂未成功|failed|error|retry',text):return Reaction('review','quota')
    if re.search(r'找到.{0,8}(原因|办法|问题|思路)|定位.{0,6}(原因|问题)|思路.{0,4}(明确|确定)|方案.{0,4}(确定|确认)|关键在于',text):return Reaction('insight','04')
    if re.search(r'检查|核对|验证|测试|查找|搜索|阅读|分析|排查|研究|查阅|inspect|search|read|test|verif',text):return Reaction('review','quota')
    return Reaction('working','22')

def tool_activity(name):
    name=str(name).lower()
    if any(v in name for v in ('search','browse','web__','fetch','view_image','read_file','read_mcp','list_','get_')):return 'research'
    if any(v in name for v in ('apply_patch','write_file','edit_file','update_file')):return 'edit'
    if any(v in name for v in ('exec_command','write_stdin','shell','terminal')):return 'execute'
    if any(v in name for v in ('imagegen','image_gen','generate')):return 'create'
    return 'tool'

class StatusReactions:
    def __init__(self,now,interval=18):
        self.interval=interval;self.next_sample=now+8;self.earliest=now
        self.latest=None;self.sessions=OrderedDict();self.completion=None
        self.seen=deque(maxlen=64);self.played=OrderedDict();self.last=None;self.last_at=-1e9;self.sample_count=0
    def configure(self,interval,now=None):
        interval=max(8,min(120,float(interval)))
        if now is not None and interval!=self.interval:self.next_sample=now+interval
        self.interval=interval
    def observe(self,event,now):
        snapshot={key:event.get(key,'') for key in ('session','turn','state','activity','text','active')}
        snapshot['text']=str(snapshot['text'])[:1000];snapshot['received']=now
        self.latest=snapshot;sid=str(snapshot['session'])
        self.sessions[sid]=snapshot;self.sessions.move_to_end(sid)
        while len(self.sessions)>32:self.sessions.popitem(last=False)
        pending=self.completion
        if pending and snapshot['state'] in ACTIVE and sid==pending.get('session',''):
            # New activity in the completed turn's session supersedes its
            # deferred celebration. Its visual notification was already sent.
            if not snapshot['turn'] or snapshot['turn']!=pending.get('turn',''):self.completion=None
    def queue_completion(self,event,now):
        key=(str(event.get('session','')),str(event.get('turn','')))
        if key!=('','') and key in self.seen:return False
        if key!=('',''):self.seen.append(key)
        self.completion=dict(session=key[0],turn=key[1],received=now)
        return True
    def finished(self,now,gap=8):
        self.earliest=max(self.earliest,now+max(0,gap))
    def busy(self,now):
        event=self.latest
        if not event or now-event['received']>90:return False
        return event['state'] in ACTIVE or isinstance(event.get('active'),(int,float)) and event['active']>0
    def poll(self,now,*,boundary,allowed=True):
        if not boundary or not allowed or now<self.earliest:return None
        if self.completion and now-self.completion['received']>120:self.completion=None
        # Explicit completion is not a stream of inferred status messages. It
        # may use the next boundary, respecting the last action's quiet gap.
        if self.completion:
            if now-self.last_at<self.interval:return None
            event=self.completion;self.completion=None
            result=Reaction('complete','18',event['session'],event['turn'])
        else:
            if now<self.next_sample:return None
            self.next_sample=now+self.interval;self.sample_count+=1
            event=self.latest
            if event and event.get('state') not in ACTIVE and event.get('active',0):
                event=next((e for e in reversed(self.sessions.values()) if e['state'] in ACTIVE and now-e['received']<=90),event)
            if not event or now-event['received']>90:return None
            selected=classify(event)
            if selected is None:return None
            result=Reaction(selected.kind,selected.action_id,str(event.get('session','')),str(event.get('turn','')))
            key=(result.session,result.turn,result.action_id)
            if now-self.played.get(key,-1e9)<60:return None
        self.last=result;self.last_at=now;self.next_sample=max(self.next_sample,now+self.interval)
        key=(result.session,result.turn,result.action_id);self.played[key]=now;self.played.move_to_end(key)
        while len(self.played)>64:self.played.popitem(last=False)
        return result
