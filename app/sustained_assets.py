"""Optional seam assets; keep logical actions separate from their playback files."""
from pathlib import Path

def seam_items(manifest):
    items=[]
    for action in manifest.get('workAnimations',[]):
        profile=action.get('sustained') if isinstance(action,dict) else None
        if not isinstance(profile,dict):continue
        name=profile.get('seamFile');frames=profile.get('seamFrames')
        if not isinstance(name,str) or not isinstance(frames,int) or isinstance(frames,bool) or not 1<=frames<=24:raise ValueError('持续动作接缝清单无效')
        items.append(dict(id=action['id']+'-seam',file=name,playbackFile=name,durationMs=round(frames*1000/24),name='持续动作接缝'))
        variants=profile.get('variants',[])
        if not isinstance(variants,list) or len(variants)>4:raise ValueError('持续动作变体清单无效')
        for index,variant in enumerate(variants):
            if not isinstance(variant,dict):raise ValueError('持续动作变体清单无效')
            extra=variant.get('seamFile');count=variant.get('seamFrames')
            if not isinstance(extra,str) or not isinstance(count,int) or isinstance(count,bool) or not 1<=count<=24:raise ValueError('持续动作变体接缝无效')
            if extra==name:continue
            items.append(dict(id=f'{action["id"]}-seam-{index}',file=extra,playbackFile=extra,durationMs=round(count*1000/24),name='持续动作变化接缝'))
    return items

def profile_paths(root,item):
    profile=item.get('sustained')
    if not isinstance(profile,dict):return None
    start,end,frames=(profile.get(k) for k in ('start','end','sourceFrames'))
    if any(not isinstance(v,int) or isinstance(v,bool) for v in (start,end,frames)) or not 0<=start<end<frames-1 or frames>2000:raise ValueError('持续动作范围无效')
    seam_count=profile.get('seamFrames')
    if not isinstance(seam_count,int) or isinstance(seam_count,bool) or not 1<=seam_count<=24:raise ValueError('持续动作接缝范围无效')
    root=Path(root).resolve();paths=[]
    for name in (item.get('playbackFile') or item['file'],profile.get('seamFile','')):
        if not isinstance(name,str) or not name:raise ValueError('持续动作素材路径无效')
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower()!='.webp':raise ValueError('持续动作素材不存在或路径无效')
        paths.append(path)
    result=dict(profile,source=paths[0],seam=paths[1])
    variants=profile.get('variants',[])
    if not isinstance(variants,list) or len(variants)>4:raise ValueError('持续动作变体清单无效')
    resolved=[]
    for variant in variants:
        if not isinstance(variant,dict) or variant.get('end')!=end or 'variants' in variant:raise ValueError('持续动作变体必须共用原片出口')
        record=profile_paths(root,dict(item,sustained=dict(variant,sourceFrames=frames)))
        resolved.append(record)
    if resolved:result['variants']=resolved
    return result
