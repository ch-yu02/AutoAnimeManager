#include "qml/RoundedCornerMaskItem.h"

#include <QSGFlatColorMaterial>
#include <QSGGeometry>
#include <QSGGeometryNode>

#include <algorithm>
#include <array>
#include <cmath>

namespace autoanime {
namespace {

constexpr int segmentsPerCorner = 12;
constexpr int vertexCount = 4 * segmentsPerCorner * 3;
constexpr qreal halfPi = 1.57079632679489661923;

struct Corner {
    QPointF outer;
    QPointF center;
    qreal startAngle;
    qreal endAngle;
};

} // namespace

RoundedCornerMaskItem::RoundedCornerMaskItem(QQuickItem *parent)
    : QQuickItem(parent)
{
    setFlag(ItemHasContents, true);
}

void RoundedCornerMaskItem::setRadius(qreal radius)
{
    radius = std::max<qreal>(0, radius);
    if (qFuzzyCompare(m_radius, radius)) {
        return;
    }
    m_radius = radius;
    update();
    emit radiusChanged();
}

void RoundedCornerMaskItem::setColor(const QColor &color)
{
    if (m_color == color) {
        return;
    }
    m_color = color;
    update();
    emit colorChanged();
}

void RoundedCornerMaskItem::geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry)
{
    QQuickItem::geometryChange(newGeometry, oldGeometry);
    if (newGeometry.size() != oldGeometry.size()) {
        update();
    }
}

QSGNode *RoundedCornerMaskItem::updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *)
{
    auto *node = static_cast<QSGGeometryNode *>(oldNode);
    if (node == nullptr) {
        node = new QSGGeometryNode;

        auto *geometry = new QSGGeometry(QSGGeometry::defaultAttributes_Point2D(), vertexCount);
        geometry->setDrawingMode(QSGGeometry::DrawTriangles);
        node->setGeometry(geometry);
        node->setFlag(QSGNode::OwnsGeometry, true);

        node->setMaterial(new QSGFlatColorMaterial);
        node->setFlag(QSGNode::OwnsMaterial, true);
    }

    const QRectF rect = boundingRect();
    const qreal radius = std::min({m_radius, rect.width() / 2, rect.height() / 2});
    auto *vertices = node->geometry()->vertexDataAsPoint2D();

    if (radius <= 0 || rect.isEmpty()) {
        for (int i = 0; i < vertexCount; ++i) {
            vertices[i].set(0, 0);
        }
    } else {
        const std::array<Corner, 4> corners{{
            {{rect.left(), rect.top()}, {rect.left() + radius, rect.top() + radius}, -halfPi, -2 * halfPi},
            {{rect.right(), rect.top()}, {rect.right() - radius, rect.top() + radius}, -halfPi, 0},
            {{rect.right(), rect.bottom()}, {rect.right() - radius, rect.bottom() - radius}, 0, halfPi},
            {{rect.left(), rect.bottom()}, {rect.left() + radius, rect.bottom() - radius}, halfPi, 2 * halfPi},
        }};

        int vertex = 0;
        for (const Corner &corner : corners) {
            for (int segment = 0; segment < segmentsPerCorner; ++segment) {
                const qreal ratio0 = static_cast<qreal>(segment) / segmentsPerCorner;
                const qreal ratio1 = static_cast<qreal>(segment + 1) / segmentsPerCorner;
                const qreal angle0 = corner.startAngle + (corner.endAngle - corner.startAngle) * ratio0;
                const qreal angle1 = corner.startAngle + (corner.endAngle - corner.startAngle) * ratio1;
                const QPointF point0 = corner.center + QPointF(std::cos(angle0), std::sin(angle0)) * radius;
                const QPointF point1 = corner.center + QPointF(std::cos(angle1), std::sin(angle1)) * radius;

                vertices[vertex++].set(static_cast<float>(corner.outer.x()), static_cast<float>(corner.outer.y()));
                vertices[vertex++].set(static_cast<float>(point0.x()), static_cast<float>(point0.y()));
                vertices[vertex++].set(static_cast<float>(point1.x()), static_cast<float>(point1.y()));
            }
        }
    }

    static_cast<QSGFlatColorMaterial *>(node->material())->setColor(m_color);
    node->markDirty(QSGNode::DirtyGeometry | QSGNode::DirtyMaterial);
    return node;
}

} // namespace autoanime
