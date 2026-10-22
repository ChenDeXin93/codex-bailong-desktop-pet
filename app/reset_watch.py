"""Public Codex Resets feed. No Codex credentials or conversation data are sent."""
import hashlib
import json
import math
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from enhanced_core import clean_text

API_URL='https://codex-resets.com/api/resets?locale=zh-CN'
SOURCE_URL='https://codex-resets.com/zh-CN'
BEIJING=timezone(timedelta(hours=8))

def epoch(value):
    try:
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            return float(value) if math.isfinite(value) and 0<value<253402271999 else None
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None:return None
        return dt.timestamp()
    except (ValueError,TypeError,OverflowError):return None

def local_time(value):
    stamp=epoch(value)
    if stamp is None:return ''
    try:return datetime.fromtimestamp(stamp,BEIJING).strftime('%m/%d %H:%M')
    except (ValueError,OSError,OverflowError):return ''

def account_reset_text(value,now=None):
    stamp=epoch(value)
    if stamp is None:return '下次重置：未提供'
    now=time.time() if now is None else now
    return ('重置时间已到 · 待刷新' if stamp<=now else '下次 '+local_time(stamp))

def normalized_item(item,scheduled=False):
    if not isinstance(item,dict):return None
    stamp=epoch(item.get('announced_at'))
    if stamp is None:return None
    text=item.get('display_text') or item.get('text') or ''
    text=clean_text(re.sub(r'https?://\S+','',text),110)
    raw_id=str(item.get('tweet_id') or '')
    ident=raw_id if re.fullmatch(r'\d{5,30}',raw_id) else hashlib.sha256(f"{stamp}|{item.get('reset_type')}".encode()).hexdigest()[:24]
    result={'id':ident,'announced':stamp,'reset_type':str(item.get('reset_type') or 'unknown')[:24], 'text':text}
    if scheduled:result['scheduled']=epoch(item.get('scheduled_for'))
    return result

def normalize_feed(data):
    if not isinstance(data,dict) or not isinstance(data.get('events'),list) or 'scheduled' not in data:
        raise ValueError('重置消息数据格式已变化')
    events=[]
    for item in data['events'][:200]:
        event=normalized_item(item)
        if event and event['id'] not in {e['id'] for e in events}:events.append(event)
    scheduled=normalized_item(data.get('scheduled'),scheduled=True)
    if data.get('scheduled') is not None and scheduled is None:
        raise ValueError('重置安排数据不完整')
    return {'events':sorted(events,key=lambda e:e['announced'],reverse=True),'scheduled':scheduled}

def schedule_key(item):
    return f"{item['id']}:{item.get('scheduled')}:{item['reset_type']}"

def pending_reset(snapshot):
    """Old cache compatibility; a passed deadline alone never resolves an announcement."""
    return (snapshot or {}).get('pending',(snapshot or {}).get('scheduled'))

def confirms(event,pending):
    return (event.get('reset_type')==pending.get('reset_type') and
            (event.get('id')==pending.get('id') or event.get('announced',0)>=pending.get('announced',0)))

def schedule_text(snapshot,now=None):
    now=time.time() if now is None else now
    item=pending_reset(snapshot)
    if not snapshot:return '下轮额外重置：正在查询…'
    if not item:return '下轮额外重置：暂未公布'
    title='备用重置' if item.get('reset_type')=='banked' else '额外重置'
    stamp=epoch(item.get('scheduled'))
    if stamp is None:return f'{title}已安排 · 时间待公布'
    if stamp<=now:return f'{title}预计 {local_time(stamp)} · 已过，待确认'
    return f'{title}预计最晚 {local_time(stamp)}（北京时间）'

def fetch_feed():
    request=urllib.request.Request(API_URL,headers={
        'User-Agent':'BailongDesktopPet/0.3.3-local (+https://codex-resets.com)',
        'Accept':'application/json', 'Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=10) as response:
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('重置消息响应过大')
        return normalize_feed(json.loads(raw.decode('utf-8')))

class ResetTracker:
    def __init__(self,path):
        self.path=Path(path)
        try:
            state=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(state,dict) or not isinstance(state.get('seen'),list):raise ValueError()
            self.state=state
        except (OSError,ValueError):self.state={'initialized':False,'seen':[],'schedules':[]}

    @property
    def snapshot(self):return self.state.get('snapshot')

    def update(self,feed,now=None):
        now=time.time() if now is None else now
        seen=set(self.state.get('seen',[]))
        schedules=set(self.state.get('schedules',[]))
        alerts=[]
        # First fetch establishes a baseline; never alert for historical resets.
        if self.state.get('initialized'):
            new=[e for e in feed['events'] if e['id'] not in seen]
            if new:
                e=new[0]
                label='备用重置额度消息' if e['reset_type']=='banked' else '额度重置消息'
                alerts.append({'kind':'confirmed','title':'Codex '+label,
                               'text':f"站点收录 {local_time(e['announced'])}：{e['text'] or '有新的重置公告，请查看来源。'}"})
        # Preserve the most recent IDs rather than arbitrary set ordering.
        ordered=list(dict.fromkeys([e['id'] for e in feed['events']]+self.state.get('seen',[])))[:256]
        schedule_ids=list(dict.fromkeys(([schedule_key(feed['scheduled'])] if feed.get('scheduled') else [])+self.state.get('schedules',[])))[:128]
        # Missing schedule data is not proof of fulfilment. Retain an announcement
        # across polls/restarts until a matching confirmed event supersedes it.
        pending=pending_reset(self.snapshot)
        resolved=list(self.state.get('resolved',[]))
        candidate=feed.get('scheduled')
        if candidate and candidate['id'] not in resolved:
            if pending is None or candidate.get('announced',0)>=pending.get('announced',0):pending=candidate
        confirmation=next((e for e in feed['events'] if pending and confirms(e,pending)),None)
        if confirmation:
            resolved=list(dict.fromkeys([pending['id']]+resolved))[:128]
            pending=None
        snapshot={'scheduled':pending,'pending':pending,'latest':feed['events'][0] if feed['events'] else None,'checked':now}
        if self.state.get('initialized') and pending and schedule_key(pending) not in schedules:
            alerts.append({'kind':'scheduled','title':'Codex 有新的重置安排','text':schedule_text(snapshot,now)})
        state={'initialized':True,'seen':ordered,'schedules':schedule_ids,'resolved':resolved,'snapshot':snapshot}
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.path)
        self.state=state
        return snapshot,alerts
