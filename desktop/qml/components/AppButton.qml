import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl
import AutoAnime 1.0

Button {
    id: control
    property string variant: "secondary"
    property string iconName: ""
    property bool selected: false
    property color foreground: {
        if (!enabled) return Theme.textDisabled
        if (variant === "primary") return Theme.accentInk
        if (variant === "danger") return Theme.screenBlack
        if (variant === "filter") return selected ? Theme.accent : Theme.textSecondary
        if (variant === "ghost") return hovered ? Theme.textPrimary : Theme.textSecondary
        return Theme.textPrimary
    }

    implicitHeight: Metrics.controlHeight
    leftPadding: iconName.length > 0 ? Metrics.space3 : Metrics.space4
    rightPadding: Metrics.space4
    spacing: Metrics.space2
    font.family: Typography.family
    font.pixelSize: Typography.label
    font.weight: Typography.medium
    icon.source: iconName.length > 0 ? "qrc:/AutoAnime/qml/icons/" + iconName + ".svg" : ""
    icon.width: 18
    icon.height: 18
    icon.color: foreground
    scale: down ? 0.98 : 1

    contentItem: IconLabel {
        spacing: control.spacing
        mirrored: control.mirrored
        display: control.display
        icon: control.icon
        text: control.text
        font: control.font
        color: control.foreground
    }
    background: Rectangle {
        radius: Metrics.radiusS
        color: {
            if (control.variant === "primary") return control.hovered ? Theme.accentHover : Theme.accent
            if (control.variant === "danger") return control.hovered ? Qt.lighter(Theme.danger, 1.08) : Theme.danger
            if (control.variant === "ghost") return control.hovered ? Theme.surfaceHover : "transparent"
            if (control.variant === "filter") {
                if (control.selected)
                    return Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.10)
                return control.hovered ? Theme.surfaceHover : Theme.surfaceLow
            }
            return control.hovered || control.selected ? Theme.surfaceHover : Theme.surface
        }
        border.width: control.activeFocus ? 2
            : (control.variant === "secondary" || control.variant === "filter" ? 1 : 0)
        border.color: control.activeFocus ? Theme.focusRing
            : (control.variant === "filter" && control.selected
                ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.28)
                : Theme.border)
        Behavior on color { ColorAnimation { duration: 140 } }
        Rectangle {
            visible: control.selected && control.variant === "ghost"
            width: 3
            height: parent.height - Metrics.space3 * 2
            radius: 2
            color: Theme.accent
            anchors.left: parent.left
            anchors.leftMargin: Metrics.space1
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
}
