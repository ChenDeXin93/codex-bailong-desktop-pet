"""Reproducible local build; no external installer compiler required."""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'app'))
from desktop_core import VERSION
from desktop_services import all_items
from release_version import validate_new_version
def build(legacy_formats=False):
    validate_new_version(VERSION)
    from asset_pack import optimize_all,CACHE
    optimized=optimize_all();optimized_by_id={v['id']:v for v in optimized['files']}
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','BailongEnhanced','--distpath','release','--workpath','build','--specpath','build','--paths','app','--exclude-module','imageio_ffmpeg','app/enhanced.py'],cwd=ROOT,check=True)
    release=ROOT/'release/BailongEnhanced'
    from package_trim import trim_qt
    trimmed=trim_qt(release)
    (ROOT/'包体优化/依赖裁剪验收.json').write_text(json.dumps(trimmed,ensure_ascii=False,indent=2),encoding='utf-8')
    # Ship the active playback assets. Raw originals remain in the source
    # project and older installed versions, rather than duplicating both sets.
    asset_root=ROOT/'outputs/白龙桌宠素材';asset_dest=release/'outputs/白龙桌宠素材'
    asset_dest.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((asset_root/'素材清单.json').read_text(encoding='utf-8'))
    shutil.copy2(asset_root/'素材清单.json',asset_dest/'素材清单.json')
    for item in all_items(manifest):
        name=item.get('playbackFile') or item['file'];source=(asset_root/name).resolve();target=(asset_dest/name).resolve()
        if not source.is_relative_to(asset_root.resolve()) or not target.is_relative_to(asset_dest.resolve()):raise ValueError('素材打包路径无效')
        record=optimized_by_id[item['id']]
        assert record['sourceSha256']==__import__('asset_pack').digest(source) and record['exactRGBA']
        packed=CACHE/(item['id']+'.webp');assert record['outputSha256']==__import__('asset_pack').digest(packed)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(packed,target)
    shutil.copy2(ROOT/'状态响应优化/更新说明.txt',release/'持续状态响应说明.txt')
    shutil.copy2(ROOT/'应用内更新/更新说明.txt',release/'应用内更新说明.txt')
    notes=ROOT/'动作质量修复/原始动作逻辑与质量基准.txt'
    shutil.copy2(ROOT/'新增动作接入/更新说明.txt',release/'新增动作与Codex联动说明.txt')
    shutil.copy2(ROOT/'发布说明/版本编号规则.json',release/'版本编号规则.json')
    shutil.copy2(ROOT/'app/licenses/upstream-v0.4.1-assets.txt',release/'上游v0.4.1素材说明.txt')
    if notes.exists():shutil.copy2(notes,release/'原始动作逻辑与质量基准.txt')
    status_notes=ROOT/'状态联动更新/规则与验收说明.txt'
    if status_notes.exists():shutil.copy2(status_notes,release/'Codex状态联动说明.txt')
    scale_notes=ROOT/'动作尺寸修复/尺寸修复说明.txt'
    if scale_notes.exists():shutil.copy2(scale_notes,release/'动作尺寸修复说明.txt')
    token_notes=ROOT/'Token图表更新/图表说明.txt'
    if token_notes.exists():shutil.copy2(token_notes,release/'Token图表说明.txt')
    height_notes=ROOT/'气泡同步过渡/过渡说明.txt'
    if height_notes.exists():shutil.copy2(height_notes,release/'气泡高度过渡说明.txt')
    details_notes=ROOT/'详情分类更新/详情分类说明.txt'
    if details_notes.exists():shutil.copy2(details_notes,release/'详情分类说明.txt')
    panel_notes=ROOT/'面板集成更新/集成说明.txt'
    if panel_notes.exists():shutil.copy2(panel_notes,release/'面板集成说明.txt')
    performance_notes=ROOT/'配色与窗口过渡/更新说明.txt'
    if performance_notes.exists():shutil.copy2(performance_notes,release/'配色过渡与性能说明.txt')
    flicker_notes=ROOT/'过渡闪烁修复/修复说明.txt'
    if flicker_notes.exists():shutil.copy2(flicker_notes,release/'过渡闪烁修复说明.txt')
    icon_notes=ROOT/'完成提醒确认/更新说明.txt'
    if icon_notes.exists():shutil.copy2(icon_notes,release/'状态图标动画说明.txt')
    report_notes=ROOT/'日报与圆环布局/更新说明.txt'
    if report_notes.exists():shutil.copy2(report_notes,release/'Token日报说明.txt')
    report_animation_notes=ROOT/'日报动画防闪烁/修复说明.txt'
    if report_animation_notes.exists():shutil.copy2(report_animation_notes,release/'日报动画修复说明.txt')
    chart_response_notes=ROOT/'日报图表响应修复/修复说明.txt'
    if chart_response_notes.exists():shutil.copy2(chart_response_notes,release/'日报图表响应修复说明.txt')
    island_notes=ROOT/'灵动岛气泡更新/更新与质量检查说明.txt'
    if island_notes.exists():shutil.copy2(island_notes,release/'灵动岛气泡与动画说明.txt')
    deployment_notes=ROOT/'一键部署更新/快速部署说明.txt'
    if deployment_notes.exists():shutil.copy2(deployment_notes,release/'快速部署说明.txt')
    shutil.copytree(ROOT/'app/sounds',release/'app/sounds',dirs_exist_ok=True)
    shutil.copytree(ROOT/'app/fonts',release/'app/fonts',dirs_exist_ok=True)
    shutil.copytree(ROOT/'app/licenses',release/'app/licenses',dirs_exist_ok=True)
    shutil.copy2(ROOT/'app/book_catalog.json',release/'app/book_catalog.json')
    shutil.copy2(ROOT/'额度卡片重设计/更新说明.txt',release/'额度卡片与快捷说明.txt')
    shutil.copy2(ROOT/'子会话完成提醒修复/更新说明.txt',release/'子会话完成提醒修复说明.txt')
    shutil.copy2(ROOT/'交互整理第一批/更新说明.txt',release/'交互整理第一批说明.txt')
    shutil.copy2(ROOT/'交互整理第二批/更新说明.txt',release/'交互整理第二批说明.txt')
    shutil.copy2(ROOT/'交互整理第三批/更新说明.txt',release/'交互整理第三批说明.txt')
    shutil.copy2(ROOT/'包体优化/更新说明.txt',release/'包体优化说明.txt')
    shutil.copy2(ROOT/'回弹过渡/更新说明.txt',release/'窗口回弹过渡说明.txt')
    shutil.copy2(ROOT/'卡片动效统一/更新说明.txt',release/'卡片动效统一说明.txt')
    shutil.copy2(ROOT/'过渡收尾修复/更新说明.txt',release/'过渡收尾修复说明.txt')
    shutil.copy2(ROOT/'胶囊双向过渡修复/更新说明.txt',release/'胶囊双向过渡修复说明.txt')
    shutil.copy2(ROOT/'动画负载与日报优化/更新说明.txt',release/'动画负载与日报优化说明.txt')
    shutil.copy2(ROOT/'收回闪烁修复/更新说明.txt',release/'收回闪烁修复说明.txt')
    shutil.copy2(ROOT/'日报概览完整展开/更新说明.txt',release/'日报概览完整展开说明.txt')
    shutil.copy2(ROOT/'开口弧额度环/更新说明.txt',release/'开口弧额度环说明.txt')
    shutil.copy2(ROOT/'三圆状态动画/更新说明.txt',release/'三圆状态动画说明.txt')
    shutil.copy2(ROOT/'状态图标连续变形/更新说明.txt',release/'状态图标连续变形说明.txt')
    shutil.copy2(ROOT/'统一刷新与精简顶栏/更新说明.txt',release/'统一刷新与精简顶栏说明.txt')
    shutil.copy2(ROOT/'Token入口精简/更新说明.txt',release/'Token入口精简说明.txt')
    shutil.copy2(ROOT/'导航标签清理/更新说明.txt',release/'导航标签清理说明.txt')
    shutil.copy2(ROOT/'视频全屏让位/更新说明.txt',release/'视频全屏让位说明.txt')
    shutil.copy2(ROOT/'视频全屏修复/更新说明.txt',release/'Firefox视频全屏修复说明.txt')
    lifecycle_notes=ROOT/'上下文压缩与会话跳转/更新说明.txt'
    if lifecycle_notes.exists():shutil.copy2(lifecycle_notes,release/'上下文压缩与会话跳转说明.txt')
    for name in ('使用说明.txt','DSH对标清单.txt','验收记录.txt'):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,release/name)
    integrity={}
    for p in sorted(release.rglob('*')):
        if p.is_file() and p.name!='payload-manifest.json':
            with p.open('rb') as stream:integrity[p.relative_to(release).as_posix()]={'bytes':p.stat().st_size,'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
    (release/'payload-manifest.json').write_text(json.dumps({'version':VERSION,'files':integrity},ensure_ascii=False),encoding='utf-8')
    payload=ROOT/'build/payload.zip'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        for path in sorted(release.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(release))
    if legacy_formats:
        shutil.copy2(payload,ROOT/f'release/白龙桌宠-{VERSION}-便携版.zip')
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onefile','--name',f'白龙桌宠-{VERSION}-安装程序','--distpath','release','--workpath','build/installer','--specpath','build','--exclude-module','imageio_ffmpeg','--add-data',str(payload)+';.','app/installer.py'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onefile','--name',f'白龙桌宠-{VERSION}-一键部署','--distpath','release','--workpath','build/quick-installer','--specpath','build','--exclude-module','imageio_ffmpeg','--add-data',str(payload.resolve())+';.','app/installer.py'],cwd=ROOT,check=True)
    files={}
    for p in (ROOT/'release').iterdir():
        if p.is_file() and p.name!='SHA256.json':
            with p.open('rb') as stream:files[p.name]=hashlib.file_digest(stream,'sha256').hexdigest()
    (ROOT/'release/SHA256.json').write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--legacy-formats',action='store_true',help='Also build portable and manual installer when explicitly needed')
    build(parser.parse_args().legacy_formats)
