# 开发与构建

Windows x64、Python 3.12。所有命令从仓库根目录的 PowerShell 执行。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-enhanced.txt
```

## 准备角色动画

Git 只存素材清单，不包含数百 MB 的动画。先运行本项目 Release 的一键部署程序；然后把已安装版本目录内的 `outputs/白龙桌宠素材` 拷贝到本仓库同名位置。可使用下面的只读导入工具：它读取安装记录定位当前版本，只复制素材，不复制设置、凭据、聊天或统计，不修改安装状态。

```powershell
.\.venv\Scripts\python.exe tools/import_installed_assets.py
```

也可用 `--source` 指定包含 `outputs/白龙桌宠素材` 的程序目录。导入当前实际播放文件后即可运行或构建；历史原始帧质量回归测试另外依赖开发原素材，Release 的播放素材不能替代全部历史基准。

```powershell
.\.venv\Scripts\python.exe app/enhanced.py
```

源码运行会使用当前 Windows 用户的桌宠设置，若已安装程序正在运行，应先从托盘退出。不要将用户数据目录加入 Git。

## 验证

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'app')
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest test_quota_summary_data test_spring_motion test_status_reactions.SchedulerTests test_ring_metrics
```

这些是无需原动画的定向检查，CI 使用相同入口。`app/test_*.py` 还包含 UI、动画、安装事务、已读识别等专项检查；部分需要完整素材、特定构建产物或历史验证夹具，不能把缺少这些条件的全量扫描宣称为通过。视频分类单元测试不替代真实播放器全屏验收。

## 构建一键部署程序

```powershell
.\.venv\Scripts\python.exe build_release.py
.\.venv\Scripts\python.exe check_bundle.py
```

构建脚本先逐帧验证并无损优化当前播放动画，再由 PyInstaller 打包运行库和安装器。产物在 `release/`，缓存在 `build/`。这两处均不提交 Git。角色动画是包体大头之一；只放 GitHub Release，避免仓库历史长期膨胀。

这里不提供自动安装、覆盖本机版本的构建后动作。要试装请运行生成的一键部署程序，先验证再替换上一版发布物；保留用户数据及已安装回退版本。

## 主要模块

| 模块 | 职责 |
| --- | --- |
| app/enhanced.py / desktop.py | 主程序、桌宠与后台服务协作 |
| enhanced_core.py / codex_live_status.py / session_read_state.py | 日志、实时状态、会话已读 |
| compact_bubble.py / surface_morph.py / panel_transition.py | 气泡、胶囊和连续窗口过渡 |
| status_indicator.py / refresh_indicator.py | 状态与刷新矢量动画 |
| token_calendar.py / token_analytics.py / daily_report.py | 增量统计与日报 |
| video_fullscreen.py / firefox_video.py / video_yield.py | 视频识别和置顶优先级 |
| installer.py / deployment_state.py / shared_assets.py | 安装事务、恢复与素材共享 |

书本等量计数工具 `tools/build_book_catalog.py` 额外需要 `tiktoken`；应用运行不需要 tokenizer，也不包含整本书文本。

原项目：https://github.com/jingh12312-rgb/bailong-desktop-pet 。授权说明见仓库根目录 NOTICE.md。
