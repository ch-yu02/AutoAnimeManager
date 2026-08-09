#include "player/MpvRenderWidget.h"

#include "player/MpvCore.h"

#include <mpv/render_gl.h>

#include <QMetaObject>
#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QWindow>

namespace autoanime {

MpvRenderWidget::MpvRenderWidget(MpvCore *core, QWidget *parent)
    : QOpenGLWidget(parent)
    , m_core(core)
{
    setMinimumSize(480, 270);
    setUpdateBehavior(QOpenGLWidget::NoPartialUpdate);
}

MpvRenderWidget::~MpvRenderWidget()
{
    releaseRenderContext();
}

void MpvRenderWidget::releaseRenderContext()
{
    if (m_renderContext == nullptr) {
        return;
    }
    if (context() != nullptr) {
        disconnect(context(), &QOpenGLContext::aboutToBeDestroyed,
                   this, &MpvRenderWidget::releaseRenderContext);
    }
    makeCurrent();
    mpv_render_context_set_update_callback(m_renderContext, nullptr, nullptr);
    mpv_render_context_free(m_renderContext);
    m_renderContext = nullptr;
    doneCurrent();
}

void MpvRenderWidget::initializeGL()
{
    mpv_opengl_init_params openGlParameters{
        &MpvRenderWidget::getProcAddress,
        nullptr,
    };
    mpv_render_param parameters[] = {
        {MPV_RENDER_PARAM_API_TYPE, const_cast<char *>(MPV_RENDER_API_TYPE_OPENGL)},
        {MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, &openGlParameters},
        {MPV_RENDER_PARAM_INVALID, nullptr},
    };
    const int result = mpv_render_context_create(
        &m_renderContext,
        m_core->nativeHandle(),
        parameters
    );
    if (result < 0) {
        emit renderError(QStringLiteral("无法创建 libmpv OpenGL Render Context"));
        return;
    }

    mpv_render_context_set_update_callback(
        m_renderContext,
        &MpvRenderWidget::onRenderUpdate,
        this
    );
    if (context() != nullptr) {
        connect(context(), &QOpenGLContext::aboutToBeDestroyed,
                this, &MpvRenderWidget::releaseRenderContext,
                Qt::DirectConnection);
    }
    emit renderReady();
}

void MpvRenderWidget::paintGL()
{
    if (m_renderContext == nullptr) {
        if (context() != nullptr && context()->functions() != nullptr) {
            context()->functions()->glClearColor(0.03F, 0.04F, 0.05F, 1.0F);
            context()->functions()->glClear(GL_COLOR_BUFFER_BIT);
        }
        m_updatePending.store(false, std::memory_order_release);
        return;
    }

    const qreal ratio = devicePixelRatioF();
    mpv_opengl_fbo framebuffer{
        static_cast<int>(defaultFramebufferObject()),
        qRound(width() * ratio),
        qRound(height() * ratio),
        0,
    };
    int flipY = 1;
    mpv_render_param parameters[] = {
        {MPV_RENDER_PARAM_OPENGL_FBO, &framebuffer},
        {MPV_RENDER_PARAM_FLIP_Y, &flipY},
        {MPV_RENDER_PARAM_INVALID, nullptr},
    };
    mpv_render_context_render(m_renderContext, parameters);
    m_updatePending.store(false, std::memory_order_release);
}

void MpvRenderWidget::maybeUpdate()
{
    if (m_renderContext == nullptr) {
        return;
    }
    if (!isVisible() || (window() != nullptr && window()->isMinimized())) {
        m_updatePending.store(false, std::memory_order_release);
        return;
    }
    update();
}

void *MpvRenderWidget::getProcAddress(void *, const char *name)
{
    QOpenGLContext *context = QOpenGLContext::currentContext();
    return context == nullptr
        ? nullptr
        : reinterpret_cast<void *>(context->getProcAddress(QByteArray(name)));
}

void MpvRenderWidget::onRenderUpdate(void *context)
{
    auto *widget = static_cast<MpvRenderWidget *>(context);
    if (widget->m_updatePending.exchange(true, std::memory_order_acq_rel)) {
        return;
    }
    QMetaObject::invokeMethod(widget, &MpvRenderWidget::maybeUpdate, Qt::QueuedConnection);
}

} // namespace autoanime
