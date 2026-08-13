# AutoAnime

单用户、本地运行的 Bangumi 自动追番与媒体管理器。当前已完成同步、媒体映射、Qt/libmpv 播放、手动与自动下载，以及“观看 → 保留 → 隔离 → 恢复或永久删除”的文件生命周期闭环。

## 环境要求

- Python 3.12+
- Node.js 22+ 与 npm 10+（仅维护可选的网页调试工具时需要）
- FFmpeg/`ffprobe`（仅用于媒体探测）
- Qt Desktop 需要 CMake、Qt 6 Base/Declarative/Quick、对应 QML 运行模块和 `libmpv-dev`，详见 `desktop/README.md`
- qBittorrent 4.1+ 或 5.x（启用 WebUI API，保持独立运行）

## 首次启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp config.example.yaml config.yaml
python -m scripts.migrate
python scripts/dev.py
```

`python scripts/dev.py` 会自动增量构建 Desktop、升级数据库、启动 FastAPI 并打开 Qt Quick 客户端；关闭窗口或按一次 `Ctrl+C` 会统一停止全部进程。首次构建时间较长，后续为增量构建。
启动器会自动优先使用仓库内 `.venv`，因此激活虚拟环境后使用 `python` 或直接使用系统 `python3` 均可。

可选启动参数：

```bash
# 已确认 Desktop 无需重新构建
python scripts/dev.py --no-build

# 直接播放指定 Episode
python scripts/dev.py --play-episode 968
```

FastAPI 文档位于 `http://127.0.0.1:8765/docs`。Vue 前端只保留为可选的后端调试工具，正式客户端不再启动或依赖它。

Windows PowerShell 激活虚拟环境时使用：

```powershell
.venv\Scripts\Activate.ps1
```

## 配置

默认读取根目录的 `config.yaml`。可通过 `AUTOANIME_CONFIG` 指定其他 YAML 文件；环境变量优先于 YAML，嵌套键使用双下划线，例如：

```bash
export AUTOANIME_APP__PORT=9000
export AUTOANIME_BANGUMI__ACCESS_TOKEN=your-token
```

未提供外部组件凭证时后端仍可启动，但 `/api/health` 和状态页会明确列出缺少项。媒体根目录在 `storage.library_roots` 中配置；扫描会递归读取允许的视频扩展名，并跳过隔离目录。qBittorrent 任务直接保存到第一个媒体根目录的 Subject 文件夹，不需要单独配置下载目录。不要提交 `config.yaml` 或 `.env`。

## 常用命令

```bash
# 完整开发环境：自动构建并启动后端与 Qt Quick Desktop
python scripts/dev.py

# 后端开发服务器
uvicorn backend.app.main:app --reload --port 8765

# 前端开发服务器
npm run dev:frontend

# 数据库迁移/回滚
alembic upgrade head
alembic downgrade base

# 后端测试
pytest

# 前端类型检查与生产构建
npm run typecheck
npm run build

# Qt/libmpv Desktop
cmake -S desktop -B desktop/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build desktop/build
ctest --test-dir desktop/build --output-on-failure

# FastAPI 已启动时单独运行原生客户端
desktop/build/autoanime-desktop

# SQLite 在线备份
python -m scripts.backup
```

运行时数据写入 `data/`。日志采用 JSON Lines 格式并滚动保留，API 返回的 Bangumi Token 和 qBittorrent 密码会被脱敏。

## 主要 API

```text
GET  /api/health
GET  /api/status
GET  /api/settings
PATCH /api/settings
POST /api/settings/test/bangumi
POST /api/settings/test/qbittorrent
POST /api/settings/test/ffprobe
POST /api/bangumi/sync
GET  /api/bangumi/sync/status
GET  /api/subjects
GET  /api/subjects/search
GET  /api/subjects/{id}
PATCH /api/subjects/{id}/collection
GET  /api/subjects/{id}/episodes
POST /api/library/scan
GET  /api/library/scan/status
GET  /api/library/files
GET  /api/library/recent
GET  /api/library/review
POST /api/library/files/{id}/match
DELETE /api/library/files/{id}/match
POST /api/library/files/{id}/ignore
POST /api/library/files/{id}/reparse
POST /api/library/files/{id}/full-hash
POST /api/playback/sessions
POST /api/playback/sessions/{session}/progress
DELETE /api/playback/sessions/{session}
GET  /api/playback/continue
GET  /api/subjects/{id}/next-unwatched
POST /api/episodes/{id}/mark-watched
POST /api/episodes/{id}/mark-unwatched
POST /api/releases/search
GET  /api/releases/search/{id}
POST /api/releases/search/{id}/debug-auto-select
POST /api/releases/candidates/{id}/download
GET  /api/scheduler
GET  /api/scheduler/runs
POST /api/scheduler/tasks/{name}/run
GET  /api/downloads
POST /api/downloads
POST /api/downloads/{id}/pause
POST /api/downloads/{id}/resume
POST /api/downloads/{id}/retry
DELETE /api/downloads/{id}
GET  /api/cleanup/candidates
GET  /api/cleanup/records
GET  /api/cleanup/subjects/{id}
PATCH /api/cleanup/subjects/{id}/keep
POST /api/cleanup/subjects/{id}/quarantine
POST /api/cleanup/records/{id}/restore
POST /api/cleanup/records/{id}/permanent-delete
```

`POST /api/bangumi/sync` 启动手动 `FULL` 同步并快速返回任务标识；Scheduler 的 `BangumiSync` 使用 `QUICK` 模式，只刷新 `DOING` 条目的 Episode 和单集观看状态。FULL 同步仍覆盖五类收藏，但缓存未变化的非在看条目，Subject 元数据默认每天刷新、关系默认每周刷新。同步请求受 `bangumi.sync_concurrency` 全局并发限制，状态接口返回模式、请求数、跳过数和耗时。Bangumi 已看会同步到本地观看状态，本地手动状态不会被远端空状态覆盖；外部 API 失败不会清空已有数据，凭证不会出现在响应或正常错误摘要中。Subject 详情可修改想看、在看、看过、搁置和抛弃：客户端先写入 Bangumi，远端成功后才更新本地；普通同步以 Bangumi 收藏状态为准，因此没有成功写入远端的本地状态不会覆盖 Bangumi。

正式 Scheduler 注册 `BangumiSync`、`LibraryScan`、`DemandRefresh`、`ReleaseSearch`、`DownloadMonitor` 和 `Cleanup`。同类任务进程内不可重入，每次执行持久化为 `TaskRun`；失败按连续次数指数退避，应用重启会将中断任务标记失败并立即安排恢复。Settings 可查看最近状态并手动执行任一任务，`GET /api/scheduler/runs` 可查看执行结果与脱敏错误。

自动资源搜索与下载 `ReleaseSearch` 默认每天执行一次；qBittorrent 状态同步 `DownloadMonitor` 仍默认每 3 秒执行。两者均可在 Settings 手动立即执行。

媒体扫描以路径、大小和修改时间判断未变化文件，只对新增或变化文件执行部分哈希、可选 `ffprobe` 和文件名解析；仅在疑似重复时计算完整哈希。低置信度、批量文件、manifest 冲突和多主文件进入审核队列。人工关联时输入中文名、原名或 alias 即时搜索，选择匹配 Subject 和 Episode 后默认锁定，并写入同目录 `manifest.json`，后续扫描不会覆盖。

在 Subject 的 Episode 行点击“搜索”会将 Bangumi 中文名、去除季度/Part 的中文基础标题、原名和 aliases 代入 `release_search.rss_url_template`，自动读取对应的 KissSub 关键词 RSS，合并并去重结果；基础标题在查询数量限制内具有优先位置，因此能覆盖只写 `3rd Season`、连续集数或不写季度的发布。系统解析条目、季度、Part、集数、字幕组、分辨率、编码、语言和批量信息，并保存候选的 score、匹配理由和排除理由；`REJECT` 仅保存在数据库用于诊断，不会显示在客户端。手动模式由用户选择候选；开启设置中的“自动下载”后，Demand Planner 只处理在看条目中已放送、未看、未忽略的 `MAIN` 单集，并且只会提交 `AUTO_ACCEPT` 候选，SP、OP、ED 等均不进入自动流程。放送未满 3 天时自动选择优先 ANi 的及时发布；满 3 天后无论是否已经下载，均优先简体、简日双语以及名称含汉字的正式字幕组，没有合适版本时才回退其他候选。Subject 已有非 ANi 媒体后，后续单集严格限定为已有字幕组，存在多个组时按相同偏好排序。Episode 放送满 3 天后若本地仍只有 ANi 版本，会继续搜索符合偏好的字幕组版本；新版本成功导入后才删除旧 ANi 媒体并移除其 qBittorrent 任务，下载失败不会删除旧文件。失败和已导入的历史下载记录不会错误阻塞重新规划。手动 magnet、40 位十六进制或 32 位 Base32 BTIH 特征码仍可直接调用下载 API。任务以 `autoanime` 分类、`bgm-{subject_id}` 和 `job-{job_id}` 标签提交；`DownloadMonitor` 在程序重启后恢复未完成任务。视频直接下载到第一媒体库目录下的 Subject 文件夹，完成后原地使用 `DOWNLOAD_JOB` 关联并写入 manifest，Episode 进入 `READY`；合集、文件数量不符或疑似单文件多集会原地进入 Library Review。成功导入不会自动清理任务。

内部配置 `release_search.debug_auto_selection_enabled` 默认关闭；仅开启后，客户端才显示“调试选择”“调试自动选择”和命中标记。调试选择使用与正式自动下载完全相同的 ANi、字幕语言、已有字幕组锁定和评分规则，只保存调试标记，不会创建 DownloadJob，也不会调用 qBittorrent。

自动清理默认关闭，开启后每天执行一次。条目只有在已确认完结、至少存在一个 MAIN Episode、现有 MAIN 全部已看且具有完成时间、完成时间超过保留期，并且没有活动下载、待审核映射或正在播放的文件时才可进入隔离区。Subject 详情可设置“永久保留”或手动隔离；客户端“隔离区”页可查看当前隔离项与历史记录、恢复文件，或经二次确认永久删除。自动永久删除会再次计算资格，只删除媒体文件，保留条目、单集、观看进度、下载与资源历史及清理日志；清理记录会说明完成单集、进入清理的时间和预计释放空间。

Qt Desktop 通过 libmpv 直接播放本地媒体，不进行网页转码；支持内封/外挂字幕、音轨切换、完整时间轴跳转和续播。播放、暂停、跳转、停止及正常结束时会保存进度。有效播放不足 60 秒不会覆盖旧进度；播放达到 90%、剩余不超过 5 分钟或正常播完时自动标记已看，手动已看/未看优先于自动判断。下一集仅在同一 Subject 的 MAIN 章节中选择已有本地文件的后续最小集数，文件删除后观看历史仍保留。

`desktop/` 包含正式的 `autoanime-desktop`。客户端由 Qt Quick/QML 构成，视频通过 libmpv Render API 成为真正的 QML Item；生产构建不依赖 Qt Widgets、QWebEngine、QWebChannel 或 DOM/native geometry overlay。
