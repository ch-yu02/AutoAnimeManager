#pragma once

#include <QPoint>
#include <QRect>
#include <QRectF>

namespace autoanime {

inline QRect playerSurfaceGeometry(
    const QPoint &webViewOrigin,
    const QRectF &cssRect,
    qreal webDevicePixelRatio,
    qreal nativeDevicePixelRatio
)
{
    const qreal safeWebRatio = webDevicePixelRatio > 0.0 ? webDevicePixelRatio : 1.0;
    const qreal safeNativeRatio = nativeDevicePixelRatio > 0.0 ? nativeDevicePixelRatio : 1.0;
    const qreal scale = safeWebRatio / safeNativeRatio;
    return QRect(
        qRound(webViewOrigin.x() + cssRect.x() * scale),
        qRound(webViewOrigin.y() + cssRect.y() * scale),
        qRound(cssRect.width() * scale),
        qRound(cssRect.height() * scale)
    );
}

} // namespace autoanime
