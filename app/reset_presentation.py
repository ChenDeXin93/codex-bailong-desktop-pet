"""Relative public reset estimates; reaching a date is never confirmation."""
import math
import time
from reset_watch import pending_reset,epoch,local_time,schedule_text

def reset_view(snapshot,error=False,now=None):
    now=time.time() if now is None else now
    item=pending_reset(snapshot);stamp=epoch((item or {}).get('scheduled'))
    title='备用重置' if (item or {}).get('reset_type')=='banked' else '额外重置'
    phase='loading';eyebrow=title;value='查询中';unit='';minutes=None;note='正在连接公告';next_change=None
    if snapshot is None:
        if error:phase='unavailable';value='暂不可用';note='稍后重试'
    elif not item:phase='empty';value='暂无安排';note='有新公告会提醒'
    elif stamp is None:phase='undated';eyebrow='已有重置安排';value='时间待定';note='等待公布具体时间'
    elif stamp<=now:phase='pending';eyebrow='预计时间已过';value='待确认';note='等待公告确认'
    else:
        phase='scheduled';eyebrow='预计还有';remaining=stamp-now;note='最晚 '+local_time(stamp)
        total_minutes=math.ceil(remaining/60)
        if total_minutes>=60:
            hours,minute=divmod(total_minutes,60);unit='小时'
            value=str(hours) if hours<=9999 else '9999+'
            if hours<=9999:minutes=f'{minute:02d}'
        else:
            unit='分钟';value='<1' if remaining<60 else str(total_minutes)
        next_change=min(remaining,remaining-(total_minutes-1)*60)
        if remaining==60:next_change=.001  # The next visible value is “<1”.
    if error and snapshot is not None:
        eyebrow='上次安排 · 预计' if phase=='scheduled' else '上次公告记录'
    parts=[(value,unit)]+([(minutes,'分钟')] if minutes is not None else [])
    main=' '.join(number+(' '+label if label else '') for number,label in parts)
    description=title+'；'+eyebrow+' '+main+'；'+schedule_text(snapshot,now)
    description+='\n北京时间 · Codex Resets（第三方）；预计安排不代表账户额度已到账。'
    if item and item.get('text'):description+='\n'+str(item['text'])
    if error:description+='\n更新失败，保留上次记录。' if snapshot is not None else '\n公告暂不可用，请稍后重试。'
    return dict(title=title,phase=phase,eyebrow=eyebrow,value=value,unit=unit,parts=parts,display=main,note=note,
                description=description,next_change=next_change)
