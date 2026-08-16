import QtQuick
import QtQuick.Controls
import AutoAnime 1.0

Slider {
    id: control
    property int trackHeight: 4
    property color trackColor: Qt.rgba(1, 1, 1, 0.24)
    property color fillColor: Theme.accent

    implicitHeight: 28
    leftPadding: 7
    rightPadding: 7

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + (control.availableHeight - height) / 2
        width: control.availableWidth
        height: control.trackHeight
        radius: height / 2
        color: control.trackColor

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: height / 2
            color: control.fillColor
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + (control.availableHeight - height) / 2
        width: control.hovered || control.pressed || control.activeFocus ? 14 : 10
        height: width
        radius: width / 2
        color: "white"
        border.width: 2
        border.color: control.fillColor
        Behavior on width { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
    }
}
