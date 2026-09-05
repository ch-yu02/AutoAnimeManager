import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

ApplicationWindow {
    id: root
    width: 560
    height: 300
    minimumWidth: 480
    minimumHeight: 260
    visible: true
    title: "AutoAnime"
    color: Theme.canvas

    Rectangle {
        anchors.fill: parent
        anchors.margins: Metrics.space6
        radius: Metrics.radiusL
        color: Theme.surface
        border.width: 1
        border.color: Theme.borderSoft

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Metrics.space6
            spacing: Metrics.space3

            Label {
                text: "AutoAnime 无法启动"
                color: Theme.textPrimary
                font.pixelSize: Typography.pageTitle
                font.weight: Typography.semibold
            }
            Label {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: startupError
                color: Theme.textSecondary
                font.pixelSize: Typography.body
                wrapMode: Text.Wrap
                verticalAlignment: Text.AlignTop
            }
            Label {
                Layout.fillWidth: true
                text: "请查看上方提示后重试。你的媒体文件不会受到影响。"
                color: Theme.textTertiary
                font.pixelSize: Typography.meta
                wrapMode: Text.Wrap
            }
            AppButton {
                Layout.alignment: Qt.AlignRight
                text: "关闭"
                variant: "primary"
                onClicked: Qt.quit()
            }
        }
    }
}
