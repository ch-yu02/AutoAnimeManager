import QtQuick
import QtQuick.Controls
import AutoAnime 1.0

Rectangle {
    id: root
    property string text: ""
    property string status: ""
    property color tone: Theme.statusColor(status)
    implicitWidth: label.implicitWidth + Metrics.space3 * 2
    implicitHeight: 22
    radius: Metrics.radiusS
    color: Qt.rgba(tone.r, tone.g, tone.b, 0.10)
    border.width: 1
    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.22)

    Label {
        id: label
        anchors.centerIn: parent
        text: root.text || root.status
        color: root.tone
        font.family: Typography.family
        font.pixelSize: Typography.micro
        font.weight: Typography.medium
    }
}
