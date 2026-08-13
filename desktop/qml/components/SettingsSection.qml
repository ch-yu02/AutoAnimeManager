import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Rectangle {
    id: root
    property string title: ""
    property string description: ""
    default property alias content: body.data
    Layout.fillWidth: true
    implicitHeight: sectionColumn.implicitHeight + Metrics.space6 * 2
    radius: Metrics.radiusM
    color: Theme.surface
    border.width: 1
    border.color: Theme.borderSoft

    ColumnLayout {
        id: sectionColumn
        anchors.fill: parent
        anchors.margins: Metrics.space6
        spacing: Metrics.space4
        Label {
            text: root.title
            color: Theme.textPrimary
            font.family: Typography.family
            font.pixelSize: Typography.sectionTitle
            font.weight: Typography.semibold
        }
        Label {
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            color: Theme.textTertiary
            font.family: Typography.family
            font.pixelSize: Typography.body
            wrapMode: Text.Wrap
        }
        ColumnLayout { id: body; Layout.fillWidth: true; spacing: Metrics.space3 }
    }
}
