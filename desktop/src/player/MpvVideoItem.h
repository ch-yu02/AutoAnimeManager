#pragma once

#include <QQuickFramebufferObject>

struct mpv_render_context;

namespace autoanime {

class MpvCore;

// Qt Quick libmpv surface. The rendering lifecycle follows KDE MpvQt and the
// official mpv QML example, adapted to share AutoAnime's existing MpvCore.
class MpvVideoItem : public QQuickFramebufferObject {
    Q_OBJECT

public:
    explicit MpvVideoItem(QQuickItem *parent = nullptr);
    Renderer *createRenderer() const override;

    static void setCore(MpvCore *core) noexcept;
    static MpvCore *core() noexcept;

    Q_INVOKABLE void requestRender();

private:
    static MpvCore *s_core;
};

} // namespace autoanime
