# Qt Quick 原生客户端

`autoanime-desktop` 是最终桌面客户端：Qt Quick/QML 负责界面，`BackendClient` 调用 FastAPI，`PlayerController` 维护播放 Session，libmpv 通过 Render API 直接渲染为 QML Item。生产路径不依赖 Vue、QWebEngine、QWebChannel 或 DOM geometry overlay。

## Ubuntu 24.04 依赖

```bash
sudo apt install cmake ninja-build g++ pkg-config qt6-base-dev qt6-declarative-dev \
  libmpv-dev qml6-module-qtqml qml6-module-qtqml-workerscript \
  qml6-module-qtquick qml6-module-qtquick-window qml6-module-qtquick-layouts \
  qml6-module-qtquick-templates qml6-module-qtquick-controls qml6-module-qtquick-dialogs
```

MpvQt 1.2 要求 Qt 6.5，而 Ubuntu 24.04 当前提供 Qt 6.4，因此本项目复用其 Render API 生命周期设计，不增加 MpvQt 二进制依赖。

## 构建与启动

```bash
cmake -S desktop -B desktop/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build desktop/build
ctest --test-dir desktop/build --output-on-failure

# 热重载开发模式
python scripts/dev.py

# 正常启动：自动迁移、启动并回收 FastAPI
desktop/build/autoanime-desktop

# 仅连接已经外部启动的 FastAPI
desktop/build/autoanime-desktop --external-backend

# 直接播放指定 Episode，用于播放基线与回归
desktop/build/autoanime-desktop --play-episode 968
```

## 播放链路

```text
PlayerPage / MpvVideoItem
→ PlayerController
→ BackendClient /api/playback/sessions
→ libmpv Render API
→ /progress
→ PlaybackStateService
```

播放器支持暂停、精确 seek、音量/静音、速度、内封音轨与字幕、外挂字幕、全屏、快捷键、前后集、EOF 自动下一集和连续切换。后端仍负责 watched、续播位置和 next Episode 业务判断。

## 人工验收

1. 首页加载继续观看与正在追，切换五种收藏标签和“只显示本地已匹配”。
2. 进入 Subject，播放 READY Episode；视频应是窗口内真正的 QML Item，控制条覆盖画面且 resize/fullscreen 不错位。
3. 检查 H.264/HEVC、24/30/60 fps、内封/外挂字幕、音轨、速度、前后集与 EOF。
4. 播放中退出，重新打开同一 Episode，应从保存位置继续；从头播放应从 0 开始。
5. Library Review 的人工关联应先输入 Subject 中文名、原名或 alias，约 300 ms 后只显示符合标题的结果；选择结果和 Episode 后保存关联。另行验证重新匹配、重新解析和忽略；Settings 可保存配置、开启 Bangumi 已看写回，并可单独开关自动下载。在 Subject 详情切换五种收藏状态，应提示已同步到 Bangumi，刷新 Bangumi 页面和本地条目分组后结果一致。
6. Settings 填写 qBittorrent WebUI 并测试连接；进入缺失 Episode，粘贴 magnet 后应直接下载到第一个媒体目录的 Subject 文件夹，完成后启用播放且保留任务记录。
7. 在下载页分别验证“仅删除下载任务”保留媒体文件、“删除任务及本地文件”删除媒体文件；下载失败后的残余文件遵循相同规则。
8. 默认不应显示自动选择调试入口和标记；在配置中设置 `release_search.debug_auto_selection_enabled: true` 并重启后，资源候选窗口应显示“调试自动选择”，点击后只标注一个 `AUTO_ACCEPT` 候选，下载页和 qBittorrent 不应新增任务。
9. 下载页应持续显示进度，暂停、继续、失败重试和删除 qBittorrent 任务有效；关闭并重启程序后未完成任务继续同步。
10. Settings 的“自动任务”应显示七类任务及最近状态（包含每日 `Backup`）；逐个点击“立即执行”应生成 `MANUAL` TaskRun，同一任务运行中按钮不可再次触发。
11. 开启自动下载后，为“在看”条目准备一个已放送、未看、无本地文件的 MAIN Episode；应自动完成搜索、下载、原地导入并变为 READY。SP、OP、ED、未放送和已看 Episode 不应创建任务。
12. Settings 的“完整同步”应覆盖五类收藏；自动任务 `BangumiSync` 应使用 QUICK 模式，仅刷新在看条目，并在状态中显示明显少于完整同步的请求数和耗时。
13. 选择一个符合清理资格的完结条目，在 Subject 详情核对清理理由、完成单集和空间；勾选“永久保留”后应立即变为不可清理，取消后可手动移入隔离区。
14. 在“隔离区”页执行“恢复”，媒体应回到原路径并可播放；再次隔离后执行“永久删除”，必须出现二次确认，删除后媒体文件消失但条目、单集、观看进度、下载记录和清理日志仍存在；切换“历史记录”可查看已恢复和已删除项。
15. 开启自动清理并缩短保留期测试 `Cleanup`：符合条件的条目自动隔离，隔离期到期后重新复核并删除；播放中、存在待审核映射或活动下载的条目不得移动或删除。
16. 开启内部调试开关后，对没有本地媒体的新 Episode 搜索同时包含 ANi 与字幕组的候选，“调试自动选择”应命中 ANi；Subject 已有非 ANi 媒体后，后续 Episode 只能命中相同字幕组，已有多个字幕组时优先简日双语、简体及名称含汉字的组。
17. 准备一个放送已满 3 天、未看且本地仅有 ANi 文件的 Episode，执行 `ReleaseSearch` 应继续搜索；符合偏好的字幕组版本成功导入后，旧 ANi 文件及其 qBittorrent 任务被删除，新文件可播放，历史 DownloadJob 仍保留。让替换下载失败时，旧 ANi 文件必须继续存在并可播放。
18. 确认 8765 端口未运行后直接启动 `desktop/build/autoanime-desktop`；客户端应自动迁移并启动后端。关闭窗口后 `/api/health` 应不可访问；若事先外部启动后端，关闭客户端不得结束该外部进程。
19. 在设置页点击“立即备份”，生成文件应位于 `data/backups` 且能通过 `PRAGMA integrity_check`；连续生成超过配置数量后只保留最近 N 份。
20. 点击“生成诊断包”，ZIP 应包含脱敏设置、近期日志、TaskRun、download/import 和 cleanup audit；搜索 Token、qBittorrent 密码和 magnet 原文均不应命中。
21. 构建 `DEB` 后安装，从 Ubuntu 应用菜单启动 AutoAnime；首次启动自动创建用户配置和数据目录，完整浏览、下载、播放、清理流程不需要 `npm`、`uvicorn`、`cmake` 或终端。
22. 临时卸载/断开外部媒体根目录后运行 `LibraryScan`，任务应失败并说明已保留记录；条目不能因此丢失本地关联。重新挂载并扫描后恢复正常。

## Ubuntu 打包

```bash
cmake -S desktop -B desktop/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build desktop/build
cpack --config desktop/build/CPackConfig.cmake
```

发布包包含 Qt/QML 客户端、backend、Alembic migrations、默认配置和仓库 Python runtime；qBittorrent 保持独立。安装版配置位于 `~/.config/AutoAnime/config.yaml`，运行数据位于 `~/.local/share/AutoAnime/data/`。

## 复用来源

- 现有 `MpvCore`、`PlayerController`、`BackendClient` 与 FastAPI Playback Session API；
- KDE MpvQt 的 `QQuickFramebufferObject`、渲染线程销毁 `mpv_render_context`、update callback 模式；
- mpv 官方 `libmpv/qml` 示例的 OpenGL proc-address、FBO Render API 和 `LC_NUMERIC=C`；
- KDE Haruna 的浮动播放控制条、双击全屏、自动隐藏 controls、轨道菜单与外挂字幕交互模式。
- AutoBangumi 的 qBittorrent 长连接会话、登录失败分类、403 单次重登录、跨 qBittorrent 4/5 的 pause/resume 兼容及重复任务确认流程。
- qBittorrent 官方 WebUI API 的 `add/info/files/filePrio/setCategory/addTags/delete` 请求契约与任务状态定义。
