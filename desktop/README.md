# Stage 3B/3C/3D/3E Qt Desktop

该目录包含独立的 3B 播放探针，以及 3C/3D/3E 正式 Desktop Shell。3B 探针验证 Qt 6、`QOpenGLWidget` 与 libmpv Render API；`autoanime-desktop` 使用 QWebEngine 加载 Vue，通过 QWebChannel 调用受限 NativeBridge，并由 Qt PlayerController 连接 FastAPI 播放 Session API。3E 让原生 `QOpenGLWidget` 按 Vue `NativePlayerSlot` 的 DOM 矩形覆盖到 WebEngine 页面内。

## 依赖

Ubuntu 24.04：

```bash
sudo apt install cmake ninja-build g++ pkg-config qt6-base-dev qt6-webengine-dev qt6-webchannel-dev libmpv-dev
```

## 构建与测试

```bash
cmake -S desktop -B desktop/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build desktop/build
ctest --test-dir desktop/build --output-on-failure
```

播放一个或多个文件：

```bash
desktop/build/autoanime-player-probe episode1.mkv episode2.mkv episode3.mkv
```

自动 smoke 验证（需要可用的图形会话，至少三个媒体文件；最后一个建议使用 15 秒以内的短视频以自然验证 EOF）：

```bash
desktop/build/autoanime-player-probe --smoke-test --subtitle episode1.chs.ass episode1.mkv episode2.mkv episode3.mkv
```

程序支持打开文件、暂停、绝对/相对 seek、音量、静音、内封音轨/字幕切换、加载外挂字幕、队列切换、全屏和播放器销毁重建。快捷键：`Space` 暂停，方向键 seek/音量，`F` 全屏，`M` 静音，`Esc` 退出全屏。

## Stage 3C/3D Desktop Shell

构建完成后运行：

```bash
# 开发模式：要求 Vite 5173 与 FastAPI 8765 已启动
desktop/build/autoanime-desktop --dev

# 可选 Chromium DevTools
desktop/build/autoanime-desktop --dev --devtools

# 生产模式：FastAPI 已提供 frontend/dist
desktop/build/autoanime-desktop

# WebEngine/OpenGL 层叠异常时使用独立原生播放窗口
desktop/build/autoanime-desktop --dedicated-player
```

Desktop 只允许 `localhost`/`127.0.0.1` 的应用页面和 `qrc` 资源导航；外部链接交给系统浏览器。窗口 geometry 保存在 `QSettings`。Vue 在普通 Chrome 中检测不到 NativeBridge 时仍可浏览和管理数据，播放提示使用 Desktop。

原生播放链路为：

```text
NativePlayer.vue
→ QWebChannel NativeBridge
→ PlayerController
→ BackendClient /api/playback/sessions
→ libmpv Render API
→ /progress
→ PlaybackStateService
```

后端 Session API 不启动 MPV，只负责验证可播放 Episode、选择 MediaFile、返回本地路径和持久化进度。Qt 在停止、切换文件和 EOF 时等待最终进度保存成功后再关闭 session，程序关闭时也会在限定时间内刷新进度；播放达到 90%、超过 60 秒或 EOF 时由现有 `PlaybackStateService` 计算已看状态。EOF 响应复用 `PlaybackStateService.next_playable()` 返回严格相邻且 READY 的下一 MAIN Episode，Vue 只按该结果决定是否自动连播，不会自行跳集。

### Stage 3E Native Video Surface

`NativePlayer.vue` 暴露 `native-player-slot`，通过 `ResizeObserver`、捕获阶段 `scroll`、窗口/Visual Viewport resize 和 route unmount 持续发送：

```text
getBoundingClientRect()
→ x / y / width / height / devicePixelRatio / visible
→ QWebChannel NativeBridge.setPlayerRect()
→ DesktopWindow 覆盖定位 MpvRenderWidget
```

Qt 按 WebEngine 页面 viewport 的坐标定位原生 Surface，并用 Web 页面 DPR 与 Qt DPR 的比例处理缩放；slot 离开视口、隐藏或卸载时 Surface 会立即隐藏。控制条仍位于视频 slot 下方，避免在两个独立渲染 Surface 之间实现 HTML 浮层。

Qt 在整页导航、刷新或 WebEngine 渲染进程退出时主动停止播放器并清除 Surface，不依赖 Vue 卸载回调。跨屏 DPI 变化会触发 Vue 重新上报 DOM Rect。若当前平台的 WebEngine/OpenGL 层叠不稳定，可使用 `--dedicated-player` 切换到独立原生播放窗口；播放、进度和 Vue 控制链路保持不变。

## 人工验收矩阵

分别用媒体库中的 H.264/HEVC、MKV/MP4、ASS 内封/外挂、多音轨和多字幕样本检查：

1. 视频直接播放且没有独立 mpv 窗口或 FFmpeg 进程；
2. seek、暂停、音量、静音和轨道选择立即生效；
3. resize 与 fullscreen 过程中画面持续正常；
4. 队列连续切换至少三集；
5. 点击“重建播放器”后仍可播放；
6. 播放中直接关闭窗口，程序无 crash、无遗留进程。

## 复用来源

Render API 初始化、OpenGL proc-address、FBO 渲染、wakeup/update callback 和 `LC_NUMERIC=C` 的实现基于 `mpv-player/mpv-examples` 中的 `libmpv/qt_opengl` 与 `libmpv/qml` 官方示例。官方示例声明其 `libmpv/` 代码可按公共领域使用；本实现按项目边界拆分了播放器核心与渲染生命周期，并增加了控制、轨道和连续切换验证。
