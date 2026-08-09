#include "player/MpvVideoItem.h"

#include "player/MpvCore.h"

#include <mpv/render_gl.h>

#include <QMetaObject>
#include <QOpenGLContext>
#include <QOpenGLFramebufferObject>
#include <QPointer>

namespace autoanime {
namespace {

void *resolveOpenGl(void *, const char *name)
{
    QOpenGLContext *context = QOpenGLContext::currentContext();
    return context == nullptr
        ? nullptr
        : reinterpret_cast<void *>(context->getProcAddress(QByteArray(name)));
}

class MpvRenderer final : public QQuickFramebufferObject::Renderer {
public:
    explicit MpvRenderer(MpvVideoItem *item)
        : m_item(item)
    {
    }

    ~MpvRenderer() override
    {
        if (m_context != nullptr) {
            mpv_render_context_set_update_callback(m_context, nullptr, nullptr);
            mpv_render_context_free(m_context);
        }
    }

    void render() override
    {
        if (!ensureContext()) {
            return;
        }
        QOpenGLFramebufferObject *target = framebufferObject();
        mpv_opengl_fbo fbo{
            static_cast<int>(target->handle()),
            target->width(),
            target->height(),
            0,
        };
        int flipY = 0;
        mpv_render_param params[] = {
            {MPV_RENDER_PARAM_OPENGL_FBO, &fbo},
            {MPV_RENDER_PARAM_FLIP_Y, &flipY},
            {MPV_RENDER_PARAM_INVALID, nullptr},
        };
        mpv_render_context_render(m_context, params);
    }

private:
    static void requestUpdate(void *context)
    {
        auto *renderer = static_cast<MpvRenderer *>(context);
        if (renderer->m_item != nullptr) {
            QMetaObject::invokeMethod(renderer->m_item, &MpvVideoItem::requestRender, Qt::QueuedConnection);
        }
    }

    bool ensureContext()
    {
        if (m_context != nullptr) {
            return true;
        }
        MpvCore *core = MpvVideoItem::core();
        if (core == nullptr || core->nativeHandle() == nullptr) {
            return false;
        }
        mpv_opengl_init_params glInit{resolveOpenGl, nullptr};
        mpv_render_param params[] = {
            {MPV_RENDER_PARAM_API_TYPE, const_cast<char *>(MPV_RENDER_API_TYPE_OPENGL)},
            {MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, &glInit},
            {MPV_RENDER_PARAM_INVALID, nullptr},
        };
        const int result = mpv_render_context_create(&m_context, core->nativeHandle(), params);
        if (result < 0) {
            m_context = nullptr;
            return false;
        }
        mpv_render_context_set_update_callback(m_context, &MpvRenderer::requestUpdate, this);
        return true;
    }

    QPointer<MpvVideoItem> m_item;
    mpv_render_context *m_context{nullptr};
};

} // namespace

MpvCore *MpvVideoItem::s_core = nullptr;

MpvVideoItem::MpvVideoItem(QQuickItem *parent)
    : QQuickFramebufferObject(parent)
{
}

QQuickFramebufferObject::Renderer *MpvVideoItem::createRenderer() const
{
    return new MpvRenderer(const_cast<MpvVideoItem *>(this));
}

void MpvVideoItem::setCore(MpvCore *core) noexcept
{
    s_core = core;
}

MpvCore *MpvVideoItem::core() noexcept
{
    return s_core;
}

void MpvVideoItem::requestRender()
{
    update();
}

} // namespace autoanime
