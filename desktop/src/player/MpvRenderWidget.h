#pragma once

#include <QOpenGLWidget>

#include <atomic>

struct mpv_render_context;

namespace autoanime {

class MpvCore;

class MpvRenderWidget final : public QOpenGLWidget {
    Q_OBJECT

public:
    explicit MpvRenderWidget(MpvCore *core, QWidget *parent = nullptr);
    ~MpvRenderWidget() override;

    [[nodiscard]] QSize sizeHint() const override { return {960, 540}; }
    void releaseRenderContext();

signals:
    void renderReady();
    void renderError(const QString &message);

protected:
    void initializeGL() override;
    void paintGL() override;

private slots:
    void maybeUpdate();

private:
    static void *getProcAddress(void *context, const char *name);
    static void onRenderUpdate(void *context);

    MpvCore *m_core;
    mpv_render_context *m_renderContext{nullptr};
    std::atomic_bool m_updatePending{false};
};

} // namespace autoanime
