import QtQuick
import AutoAnime 1.0

Item {
    id: root
    property alias source: image.source
    property alias fillMode: image.fillMode
    property alias asynchronous: image.asynchronous
    property alias sourceSize: image.sourceSize
    property alias status: image.status
    property real radius: Metrics.radiusM
    property color cornerColor: Theme.canvas

    Image {
        id: image
        anchors.fill: parent
    }

    Canvas {
        id: cornerMask
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative

        function addCornerMasks(context, width, height, radius) {
            context.beginPath()
            context.moveTo(0, radius)
            context.lineTo(0, 0)
            context.lineTo(radius, 0)
            context.arc(radius, radius, radius, -Math.PI / 2, -Math.PI, true)
            context.closePath()

            context.moveTo(width - radius, 0)
            context.lineTo(width, 0)
            context.lineTo(width, radius)
            context.arc(width - radius, radius, radius, 0, -Math.PI / 2, true)
            context.closePath()

            context.moveTo(width, height - radius)
            context.lineTo(width, height)
            context.lineTo(width - radius, height)
            context.arc(width - radius, height - radius, radius, Math.PI / 2, 0, true)
            context.closePath()

            context.moveTo(radius, height)
            context.lineTo(0, height)
            context.lineTo(0, height - radius)
            context.arc(radius, height - radius, radius, Math.PI, Math.PI / 2, true)
            context.closePath()
        }

        onPaint: {
            const context = getContext("2d")
            context.reset()
            context.fillStyle = root.cornerColor
            addCornerMasks(context, width, height, Math.min(root.radius, width / 2, height / 2))
            context.fill()
        }
    }

    onCornerColorChanged: cornerMask.requestPaint()
    onRadiusChanged: cornerMask.requestPaint()
}
