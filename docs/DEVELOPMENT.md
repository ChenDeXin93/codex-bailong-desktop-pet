# 开发与构建

Windows x64，Python 3.12（当前本地冻结环境为3.12.14）。先安装 requirements-enhanced.txt，所有命令从仓库根目录执行。原项目与授权边界见根目录 NOTICE.md。

## 准备动画

Git不保存大型动画。安装正式版本后，在设置中下载高清素材，再执行 `python tools/import_installed_assets.py`：工具验证并导入高清源和循环接缝，不读取账户、聊天或统计。也可以从 materials Release 下载高清ZIP，解压到 `outputs/白龙桌宠素材/`，其下应直接存在素材清单和quality各目录。不要把512px轻量素材冒充720px构建源。

当前共有25个逻辑动作和6段循环接缝。导入工具支持 `--source` 指向已解压高清目录或含outputs目录的旧高清程序。旧历史质量回归另需原始开发帧；发布播放素材不能替代全部历史夹具。

## 本地迭代

`python app/enhanced.py` 运行源码；会使用本用户桌宠数据，测试请隔离LOCALAPPDATA/CODEX_HOME，避免与正在运行的正式程序混用。

`python build_local.py --build-only` 完整检查并构建应用目录；`python build_local.py --deploy-verified` 实装刚验证且源码未变的构建，备份用户数据并保留回退。默认不生成公开安装器或ZIP。完整历史回归需要开发素材和夹具，干净仓库不能宣称全量708项都可直接运行。

最终EXE另做离线TLS初始化自检，要求证书和主机名校验开启。构建工具会保留解释器SSL实现依赖的附属数据文件；不要用关闭验证来替代补齐运行依赖。

`python build_release.py` 仅构建应用目录，不改变本机安装。公开发布前先构建并校验完整Windows包、program.zip / program.json及 SHA256SUMS，再运行 `build_card_only.package()` 生成仅卡片安装包和独立轻量资源。仅卡片安装包需先验证素材ID、载荷清单和所有文件校验值；轻量资源以 materials-ID 预发布单独上传，软件稳定版随后发布。`python check_bundle.py` 比对编译模块。输出与缓存不提交Git。

程序小包只省略明确匹配的动画素材，所有程序/运行库/字体来自新包。按更新内容选择附件：程序补丁提供 program.zip、program.json 和 SHA256SUMS；动画补丁提供 animation.json、轻量/高清动画 ZIP 和 SHA256SUMS。同批发布在一个稳定 Release 内共用版本。完整 Windows 包和仅卡片安装包作为安装基包按需更新，保留明确的首次安装链接；旧客户端迁移、新安装及不兼容情况使用安装基包。高清按内容ID单独发布为预发布且不设Latest，不能让资源标签取代软件稳定版。

## 补丁编号与显示名称

公开补丁统一编号（2026-10-25）：程序补丁包和动画补丁包共用 GitHub 公开版本序列。单独发布任一类补丁都从上一个公开发布版本进一位；同批发布两类补丁共用一个版本号。对外显示“程序补丁包 1.0.1”“动画补丁包 1.0.2”；同时发布则两包均为同一新版本。第三段、第二段均只用 0—9，按既定规则进位。本地开发版独立编号。程序内部版本、更新描述和 GitHub 标签必须与本次公开版本一致；动画内容 ID 是校验标识，不另占一个公开版本号。底层下载文件名保持更新器兼容格式，使用 Release 标题及附件 label 展示用户名称。

动画补丁独立发现、后台校验、按画质下载、动作结束后切换和素材回退已在本地开发版接入，API 受限时支持补丁下载备用通道。当前公开 v1.0.0 尚不包含这套新路由：须先发布程序补丁交付新版更新器，动画描述 minimumProgramVersion 必须填写实际已公开且具备该能力的程序版本。跳过该程序版本的旧客户端仍需用安装基包或明确的程序升级链接升级，不能宣称旧客户端已自动具备该能力。具体构建协议见 [补丁发布](PATCH_RELEASES.md)。

## 不依赖外部动画的检查

在PowerShell设置 `$env:PYTHONPATH='app'` 与 `$env:QT_QPA_PLATFORM='offscreen'`，然后运行 `.github/workflows/checks.yml` 中列出的unittest模块。CI使用相同入口并编译检查app与tools；涉及真实桌面、安装、历史素材及浏览器的验收另行运行。

## WSL 来源

Windows 主程序可选择一个 WSL 发行版和用户，读取 Linux 会话日志并在发行版内调用 CLI。来源切换必须重启，Windows 实时管道与自动已读不适用。入口、权限、性能和验收边界见 [WSL 接入](WSL.md)。

## 关键模块

| 模块 | 作用 |
| --- | --- |
| desktop / enhanced | 人物、卡片、后台服务与生命周期 |
| stream_player / sustained_player / decode_runtime / loop_cache | 有界解码、共用中段和尾部读取、高精度帧时钟、异步取消及压缩循环缓存 |
| continuous_work / status_reactions | 稳定语义与主会话优先、完整尾部和完成优先 |
| compact_bubble / surface_morph / linked_report_motion | 胶囊、卡片和日报原生交接 |
| token_analytics / daily_report | 增量统计、小时/模型与日报 |
| material_store / material_controller | 轻量默认、高清校验和安全切换 |
| app_updates / program_updates / program_update_apply | 完整/程序更新、素材兼容检查、事务安装与回退 |
| installer / deployment_state / shared_assets | nonce就绪、用户数据备份、入口切换与素材复用 |

人物帧时钟使用perf_counter，业务状态保留monotonic，不能混算绝对值。取消只发停止信号，GUI不等待旧解码线程；每个生产者独立队列，旧任务不可发布新缓存。24MiB只是压缩循环缓存预算，不是进程总内存。

## 高清资源构建

可本地运行 `python build_materials.py --package-hd`，会验证源帧并生成独立资源ZIP。仓库还提供手动触发的Publish HD materials工作流：读取已公开且固定SHA的v0.7.2基包、当前素材清单及六段已验证接缝输入；把旧安装器当数据读取，不执行它。每个素材逐一校验，最终ZIP需与本地规范组装SHA一致，上传完整后再公开资源预发布，不修改稳定Latest。此工作流只针对当前内容版本；后续换源须重新评审和验证。

书本等量工具额外需要tiktoken；应用本身不打包整本书或tokenizer。不得提交凭据、真实会话、日志、用户数据库、运行配置或安装器。
