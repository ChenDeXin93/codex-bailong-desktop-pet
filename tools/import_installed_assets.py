"""Copy only active animation assets from a locally installed release."""
import argparse,json,os,shutil
from pathlib import Path

def import_assets(source,dest):
    source=Path(source).resolve()/'outputs/白龙桌宠素材'
    dest=Path(dest).resolve()/'outputs/白龙桌宠素材'
    data=json.loads((source/'素材清单.json').read_text(encoding='utf-8'))
    items=[data['idle']]+data.get('additionalIdleAnimations',[])+data['variants']
    items.extend(data[key] for key in ('quotaAnimation','dragAnimation','landingAnimation') if data.get(key))
    names={item.get('playbackFile') or item['file'] for item in items}
    pairs=[]
    for name in sorted(names):
        src=(source/name).resolve();out=(dest/name).resolve()
        if not src.is_relative_to(source) or not out.is_relative_to(dest):raise ValueError('素材路径越界')
        if not src.is_file():raise FileNotFoundError(src)
        pairs.append((src,out))
    for src,out in pairs:
        out.parent.mkdir(parents=True,exist_ok=True)
        if src!=out:shutil.copy2(src,out)
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/'素材清单.json',dest/'素材清单.json')
    print(f'已导入 {len(pairs)} 段当前播放素材；未读取设置、账号、聊天或统计。')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path)
    args=parser.parse_args();source=args.source
    if source is None:
        root=Path(os.environ['LOCALAPPDATA'])/'Programs/BailongEnhanced'
        record=json.loads((root/'installations.json').read_text(encoding='utf-8'))
        source=(root/'versions'/record['current']).resolve()
        if source.parent!=(root/'versions').resolve():raise ValueError('安装路径无效')
    import_assets(source,Path(__file__).resolve().parents[1])
