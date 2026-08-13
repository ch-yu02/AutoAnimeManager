import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

ColumnLayout {
    id: root
    property string title: "暂无内容"
    property string detail: ""
    property string iconName: "inbox"
    property string actionText: ""
    signal actionClicked()
    spacing: Metrics.space3

    Image {
        Layout.alignment: Qt.AlignHCenter
        source: "qrc:/AutoAnime/qml/icons/" + root.iconName + ".svg"
        sourceSize.width: 32
        sourceSize.height: 32
        opacity: 0.55
    }
    Label {
        Layout.alignment: Qt.AlignHCenter
        text: root.title
        color: Theme.textSecondary
        font.family: Typography.family
        font.pixelSize: Typography.itemTitle
        font.weight: Typography.semibold
    }
    Label {
        Layout.alignment: Qt.AlignHCenter
        Layout.maximumWidth: 440
        visible: text.length > 0
        text: root.detail
        color: Theme.textTertiary
        font.family: Typography.family
        font.pixelSize: Typography.body
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
    AppButton {
        Layout.alignment: Qt.AlignHCenter
        visible: root.actionText.length > 0
        text: root.actionText
        onClicked: root.actionClicked()
    }
}
