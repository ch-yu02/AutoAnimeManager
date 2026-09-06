# AutoAnimeManager

面向个人动画媒体库的原生桌面客户端。连接 Bangumi、RSS 和 qBittorrent，把收藏同步、资源检索、下载、媒体匹配、播放进度与文件清理串成一条本地工作流。

> 当前主要面向 Ubuntu 24.04 和单用户本地部署。项目仍在持续开发，请在启用自动下载或自动清理前备份媒体和数据库。

## 功能

- **原生播放**：Qt Quick + libmpv 直接播放 MKV、HEVC 和本地字幕，无需转码；支持续播、完整时间轴、音轨/字幕切换和播放期间休眠抑制。
- **Bangumi 同步**：同步五类收藏、Subject、Episode 与观看状态；客户端修改收藏或已看状态后可写回 Bangumi。
- **媒体库管理**：递归扫描媒体目录，自动解析并匹配 Subject/Episode；低置信度结果进入审核页，支持搜索后人工关联、忽略和重新匹配。
- **下载闭环**：根据 Bangumi 标题与 aliases 检索专属 RSS，支持候选选择、磁力链接和 BTIH；qBittorrent 直接下载到媒体库并自动关联 Episode。
- **自动追番**：仅处理“在看”条目中已放送、未看且缺少本地媒体的 MAIN Episode；优先中文正式字幕组，并支持 ANi 临时版本的后续替换。
- **文件生命周期**：看完后按策略移入隔离区，可恢复、永久保留或二次确认后删除；条目、观看历史和清理记录继续保留。
- **长期运行**：客户端自行迁移并启动 FastAPI，退出时优雅回收；任务中断后按审计记录恢复，数据库每日校验备份。
- **诊断与发布**：设置页可一键生成脱敏诊断包；Ubuntu 发布包包含 Qt 客户端、Python runtime、后端与迁移文件。
- **多主题界面**：提供深色与浅色主题，页面、组件和交互状态使用统一设计系统。

## 工作方式

```text
Bangumi ──收藏 / Episode / 观看状态──┐
RSS ─────资源候选───────────────────┼─ FastAPI + SQLite ─ Qt Quick 客户端
qBittorrent ─下载状态 / 本地文件────┘                      │
                                                         └─ libmpv 直接播放
```

FastAPI 负责同步、匹配、调度和文件生命周期；Qt Quick 客户端负责浏览、审核和播放。视频由 libmpv Render API 直接渲染为 QML Item，不依赖 QWebEngine、WebChannel 或网页转码。

## 快速开始

### 安装发布包（普通使用）

Ubuntu 24.04 安装项目发布的 `.deb` 后，从应用菜单打开 **AutoAnime** 即可。客户端会自动：

```text
升级 SQLite → 启动 FastAPI → 等待健康检查 → 打开界面
```

关闭窗口会停止由客户端启动的后端。qBittorrent 仍需独立安装并启用 WebUI；日常使用不需要运行 `uvicorn`、`cmake`、`npm` 或终端命令。

首次启动的用户配置位于 `~/.config/AutoAnime/config.yaml`，运行数据位于 `~/.local/share/AutoAnime/data/`。

### 从源码开发

#### 1. 安装系统依赖

Ubuntu 24.04：

```bash
sudo apt install python3-venv cmake ninja-build g++ pkg-config ffmpeg \
  qt6-base-dev qt6-declarative-dev libmpv-dev \
  qml6-module-qtqml qml6-module-qtqml-workerscript \
  qml6-module-qtquick qml6-module-qtquick-window qml6-module-qtquick-layouts \
  qml6-module-qtquick-templates qml6-module-qtquick-controls \
  qml6-module-qtquick-dialogs
```

自动下载还需要独立运行的 qBittorrent，并启用 WebUI API。

#### 2. 初始化项目

```bash
git clone https://github.com/ch-yu02/AutoAnimeManager.git
cd AutoAnimeManager

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

cp config.example.yaml config.yaml
python -m scripts.migrate
python scripts/dev.py
```

`scripts/dev.py` 保留热重载式开发流程。完成一次构建后，也可直接运行 `desktop/build/autoanime-desktop`：客户端会自行升级数据库、启动 FastAPI 并在退出时回收后端。

## 配置

编辑根目录的 `config.yaml`，至少确认以下内容：

- `bangumi.username` 与 `bangumi.access_token`
- `storage.library_roots`
- `qbittorrent.base_url`、用户名和密码
- `release_search.sources`（默认启用 KissSub、Comicat 和 AcgnX）

客户端设置页可维护常用配置并测试 Bangumi、qBittorrent 和 `ffprobe` 连接。自动下载与自动清理默认关闭，建议先完成媒体扫描和人工审核后再启用。

数据库默认每天在线备份一次，完成后执行 SQLite `integrity_check`，并只保留最近 7 份。设置页的“备份与诊断”可立即备份或生成 ZIP；诊断包只包含脱敏配置、近期日志、TaskRun 以及 download/import/cleanup 审计，不包含 Token、密码或 magnet。

外部媒体挂载暂时离线时，扫描任务会记录失败并保留该根目录下的现有媒体关联，不会把整块离线媒体库误判为已删除；挂载恢复后可手动重新扫描。

环境变量会覆盖 YAML，嵌套键使用双下划线：

```bash
export AUTOANIME_APP__PORT=9000
export AUTOANIME_BANGUMI__ACCESS_TOKEN=your-token
```

需要代理访问 Bangumi、Comicat 和 AcgnX 时，在启动客户端的同一环境设置标准代理变量。Bangumi API、Qt 封面请求、Comicat 和 AcgnX 会使用代理；KissSub、本地 FastAPI 和 qBittorrent 保持直连：

```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
autoanime-desktop
```

不要提交 `config.yaml`、`.env`、数据库或媒体文件。

## 开发

```bash
# 完整开发环境
python scripts/dev.py

# 已构建过且本次未修改 C++、QML、CMake 或桌面资源
python scripts/dev.py --no-build

# 后端测试
pytest

# 原生客户端构建与测试
cmake -S desktop -B desktop/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build desktop/build
ctest --test-dir desktop/build --output-on-failure

# 生成 Ubuntu DEB 与通用 TGZ（输出在 desktop/build）
cpack --config desktop/build/CPackConfig.cmake
```

FastAPI 启动后可在 <http://127.0.0.1:8765/docs> 查看完整接口。桌面端依赖、播放链路和人工验收步骤见 [`desktop/README.md`](desktop/README.md)。

## 数据与安全

运行数据默认位于 `data/`：SQLite 数据库、日志、缓存、备份和隔离文件均不会进入 Git。日志采用 JSON Lines 并滚动保留，API 响应会对 Bangumi Token 和 qBittorrent 密码脱敏。

涉及媒体删除的操作先进入隔离区或要求二次确认，但这不能替代独立备份。

## 参考与致谢

项目在实现与交互设计中参考了以下公开项目和文档：

- [mpv](https://github.com/mpv-player/mpv) 的 libmpv Render API 与 QML 示例
- [MpvQt](https://invent.kde.org/libraries/mpvqt) 的渲染生命周期设计
- [Haruna](https://invent.kde.org/multimedia/haruna) 的原生播放器交互
- [Jellyfin Media Player](https://github.com/jellyfin/jellyfin-media-player) 的桌面媒体客户端架构
- [AutoBangumi](https://github.com/EstrellaXD/Auto_Bangumi) 的自动追番与 qBittorrent 集成思路
- [Lucide](https://lucide.dev/) 图标集

各项第三方许可与具体复用范围见 [`desktop/THIRD_PARTY_NOTICES.md`](desktop/THIRD_PARTY_NOTICES.md)。
