# 阶段 1 播放基线

测试环境：Ubuntu 24.04、Qt 6.4.2、mpv 0.37/libmpv 2.2、AMD Radeon 780M OpenGL 4.6。测试日期 2026-08-09。

## 样本

| 样本 | 编码 | 帧率 | 像素格式 | 封装/字幕 |
| --- | --- | ---: | --- | --- |
| 魔都精兵的奴隶 S2 EP1 | H.264 1080p | 23.976 | yuv420p | MP4 |
| 新 吊带袜天使 EP2 | HEVC 10-bit 1080p | 23.976 | yuv420p10le | MKV / ASSx2 |
| 无职转生 S2 EP16 | H.264 1080p | 60 | yuv420p | MP4 / 内封字幕 |

## 结果

| 路径 | 结果 |
| --- | --- |
| mpv CLI | HEVC 10-bit 使用 `hevc-vaapi`；H.264 60 fps 使用 `h264-vaapi`，5 秒样本均正常完成。 |
| `autoanime-player-probe` | 阶段迁移前用于独立 Qt/libmpv 对照；完成基线后已随旧 `QOpenGLWidget` 播放实现删除。 |
| 旧 WebEngine Desktop | 已确认存在交互卡顿、画面掉帧感和 overlay 错位；该路径按开发计划退出生产构建，不再继续调优。 |
| QML Player | HEVC 10-bit 实际播放报告 `hwdec=nvdec-copy`、`dropped_frames=0`；内封 ASS 字幕正常，视频与 controls 位于同一 Qt Quick Scene。H.264 实际续播从 766.89 秒恢复，并持续保存到 1006.55 秒。 |

实际窗口已检查 resize 后画面比例、字幕合成和视频方向。全屏、轨道切换、外挂字幕以及 24/30/60 fps 长时间稳定性仍应按 `desktop/README.md` 的人工矩阵在目标桌面会话复验；Player 顶部实时显示硬解方式和 dropped frames，便于对比同一文件。
