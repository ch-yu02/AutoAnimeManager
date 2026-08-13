import QtQuick
import AutoAnime 1.0

Item {
    id: root
    property real value: 0

    implicitHeight: 4

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.progressTrack

        Rectangle {
            width: parent.width * Math.max(0, Math.min(1, root.value))
            height: parent.height
            radius: height / 2
            color: Theme.accent
        }
    }
}
