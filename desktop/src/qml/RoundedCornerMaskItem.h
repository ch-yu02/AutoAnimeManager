#pragma once

#include <QColor>
#include <QQuickItem>

namespace autoanime {

class RoundedCornerMaskItem : public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(qreal radius READ radius WRITE setRadius NOTIFY radiusChanged)
    Q_PROPERTY(QColor color READ color WRITE setColor NOTIFY colorChanged)

public:
    explicit RoundedCornerMaskItem(QQuickItem *parent = nullptr);

    qreal radius() const noexcept { return m_radius; }
    void setRadius(qreal radius);

    QColor color() const noexcept { return m_color; }
    void setColor(const QColor &color);

signals:
    void radiusChanged();
    void colorChanged();

protected:
    QSGNode *updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *) override;
    void geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry) override;

private:
    qreal m_radius{0};
    QColor m_color{Qt::transparent};
};

} // namespace autoanime
