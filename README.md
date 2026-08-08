# AutoAnime

单用户、本地运行的 Bangumi 自动追番与媒体管理器。当前完成阶段 2：除 Bangumi 元数据与收藏同步外，已支持本地媒体扫描、章节匹配、manifest 和人工审核；下载和播放将在后续阶段实现。

## 环境要求

- Python 3.12+
- Node.js 22+
- npm 10+
- 可选安装 FFmpeg（使用 `ffprobe` 补充时长、编码和分辨率）
- 后续阶段需要独立安装 qBittorrent 和 MPV；阶段 2 不要求它们可用

## 首次启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp config.example.yaml config.yaml
python -m scripts.migrate
npm install
python scripts/dev.py
```

打开 `http://127.0.0.1:5173`。FastAPI 文档位于 `http://127.0.0.1:8765/docs`。

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

未提供外部组件凭证时后端仍可启动，但 `/api/health` 和状态页会明确列出缺少项。媒体根目录在 `storage.library_roots` 中配置；扫描会递归读取允许的视频扩展名，并跳过下载与隔离目录。不要提交 `config.yaml` 或 `.env`。

## 常用命令

```bash
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
POST /api/settings/test/mpv
POST /api/bangumi/sync
GET  /api/bangumi/sync/status
GET  /api/subjects
GET  /api/subjects/{id}
GET  /api/subjects/{id}/episodes
POST /api/library/scan
GET  /api/library/scan/status
GET  /api/library/files
GET  /api/library/review
POST /api/library/files/{id}/match
DELETE /api/library/files/{id}/match
POST /api/library/files/{id}/ignore
POST /api/library/files/{id}/reparse
POST /api/library/files/{id}/full-hash
```

`POST /api/bangumi/sync` 会快速返回任务标识；通过状态接口查看成功、部分失败或失败及脱敏错误摘要。同步仅保存符合范围的 Bangumi 收藏，使用 Bangumi ID 幂等更新 Subject、Episode 和关系，外部 API 失败不会清空已有数据。Bangumi Token 和 qBittorrent 密码不会出现在 API 响应或正常错误摘要中。

媒体扫描以路径、大小和修改时间判断未变化文件，只对新增或变化文件执行部分哈希、可选 `ffprobe` 和文件名解析；仅在疑似重复时计算完整哈希。低置信度、批量文件、manifest 冲突和多主文件进入审核队列。人工关联默认锁定，并写入同目录 `manifest.json`，后续扫描不会覆盖。
