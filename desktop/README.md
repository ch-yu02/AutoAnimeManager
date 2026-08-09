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

# 推荐：统一启动 FastAPI 与客户端
python scripts/dev.py

# FastAPI 已运行时单独启动
desktop/build/autoanime-desktop

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
5. Library Review 执行重新匹配、人工关联、重新解析和忽略；Settings 可保存现有后端支持的配置。

## 复用来源

- 现有 `MpvCore`、`PlayerController`、`BackendClient` 与 FastAPI Playback Session API；
- KDE MpvQt 的 `QQuickFramebufferObject`、渲染线程销毁 `mpv_render_context`、update callback 模式；
- mpv 官方 `libmpv/qml` 示例的 OpenGL proc-address、FBO Render API 和 `LC_NUMERIC=C`；
- KDE Haruna 的浮动播放控制条、双击全屏、自动隐藏 controls、轨道菜单与外挂字幕交互模式。
