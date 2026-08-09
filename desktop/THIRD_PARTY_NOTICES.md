# 参考项目说明

阶段 1 实现评估并参考了以下官方项目：

- [mpv-player/mpv-examples](https://github.com/mpv-player/mpv-examples)：`libmpv/qml` 与 `libmpv/qt_opengl` 示例；其 README 将 `libmpv/` 示例声明为 public domain。实际复用了 OpenGL proc-address、FBO Render API、update callback 和 `LC_NUMERIC=C` 的集成方式。
- [KDE MpvQt](https://invent.kde.org/libraries/mpvqt)：LGPL-2.1-only OR LGPL-3.0-only OR KDE-Accepted-LGPL。参考了 `QQuickFramebufferObject` 的 render-thread 生命周期、render context 在渲染线程释放以及 core/render context 的销毁顺序；因当前 Qt 6.4 低于 MpvQt 1.2 所需 Qt 6.5，没有直接复制或打包 MpvQt 源码。
- [KDE Haruna](https://invent.kde.org/multimedia/haruna)：GPL-3.0-or-later。只参考播放器交互设计，包括 controls 自动隐藏、双击全屏、轨道菜单和外挂字幕入口，没有复制或打包 Haruna 源码、QML 或 KDE 依赖。

项目内部继续复用了已有 `MpvCore`、`PlayerController`、`BackendClient`、Playback Session API 与 `PlaybackStateService`，没有在 QML/C++ 重写 watched、续播位置或 next Episode 业务规则。
