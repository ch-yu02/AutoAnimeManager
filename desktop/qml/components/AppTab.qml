import QtQuick
import QtQuick.Controls
import AutoAnime 1.0

TabButton {
    id: control
    property bool selected: checked
    implicitHeight: Metrics.controlHeight
    leftPadding: Metrics.space3
    rightPadding: Metrics.space3
    font.family: Typography.family
    font.pixelSize: Typography.label
    font.weight: selected ? Typography.semibold : Typography.medium
    contentItem: Label {
        text: control.text
        color: control.selected ? Theme.textPrimary : (control.hovered ? Theme.textSecondary : Theme.textTertiary)
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        color: control.hovered ? Qt.rgba(1, 1, 1, 0.025) : "transparent"
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: control.selected ? 2 : 1
            color: control.selected ? Theme.accent : Theme.borderSoft
        }
        Rectangle {
            anchors.fill: parent
            color: "transparent"
            border.width: control.activeFocus ? 2 : 0
            border.color: Theme.focusRing
            radius: Metrics.radiusS
        }
    }
}
