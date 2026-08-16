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

    RoundedCornerMaskItem {
        anchors.fill: parent
        radius: root.radius
        color: root.cornerColor
    }
}
