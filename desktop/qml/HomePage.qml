import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    signal openSubject(int id)
    signal playEpisode(int id, string title)
    contentWidth: availableWidth

    ColumnLayout {
        x: 32
        width: root.availableWidth - 64
        spacing: 24

        RowLayout {
            Layout.fillWidth: true
            Label { text: "晚上好"; color: "#f2f5f8"; font.pixelSize: 32; font.weight: Font.DemiBold }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: backend.busy; visible: running; implicitWidth: 32; implicitHeight: 32 }
            Button { text: "刷新"; onClicked: backend.loadHome() }
        }
        Label { text: "继续观看"; color: "#f2f5f8"; font.pixelSize: 21; font.weight: Font.DemiBold }
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: 178
            contentWidth: continueRow.implicitWidth
            clip: true
            Row {
                id: continueRow
                spacing: 14
                Repeater {
                    model: backend.continueWatching
                    delegate: Rectangle {
                        required property var modelData
                        width: 330; height: 160; radius: 10; color: "#121a25"
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 12; spacing: 14
                            Image { Layout.preferredWidth: 90; Layout.fillHeight: true; source: modelData.subject.image_url || ""; fillMode: Image.PreserveAspectCrop }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { Layout.fillWidth: true; text: modelData.subject.name; color: "#f2f5f8"; elide: Text.ElideRight; font.pixelSize: 16; font.weight: Font.DemiBold }
                                Label { Layout.fillWidth: true; text: "第 " + modelData.episode.display_number + " 集"; color: "#93a1b2"; elide: Text.ElideRight }
                                ProgressBar { Layout.fillWidth: true; value: modelData.progress_ratio || 0 }
                                Button { text: modelData.playable ? "继续观看" : "文件缺失"; enabled: modelData.playable; onClicked: root.playEpisode(modelData.episode_id, modelData.subject.name) }
                            }
                        }
                    }
                }
                Label { visible: backend.continueWatching.length === 0; text: "暂无未完成的观看记录"; color: "#93a1b2" }
            }
        }
        Label { text: "正在追"; color: "#f2f5f8"; font.pixelSize: 21; font.weight: Font.DemiBold }
        Flow {
            Layout.fillWidth: true
            spacing: 14
            Repeater {
                model: backend.doingSubjects.slice(0, 12)
                delegate: MediaCard { required property var modelData; itemData: modelData; onClicked: root.openSubject(modelData.id) }
            }
        }
        Label { text: "最近入库"; color: "#f2f5f8"; font.pixelSize: 21; font.weight: Font.DemiBold }
        Flow {
            Layout.fillWidth: true
            spacing: 14
            Repeater {
                model: backend.recentMedia
                delegate: MediaCard {
                    required property var modelData
                    itemData: ({
                        image_url: modelData.subject ? modelData.subject.image_url : "",
                        display_name: modelData.subject ? modelData.subject.name : modelData.filename
                    })
                    onClicked: { if (modelData.subject) root.openSubject(modelData.subject.id) }
                }
            }
        }
        Label {
            property int count: (backend.review.needs_review || []).length
            text: count > 0 ? "媒体库有 " + count + " 个文件待审核" : "媒体库没有待审核文件"
            color: count > 0 ? "#f4c878" : "#72d5b4"
        }
        Item { Layout.preferredHeight: 24 }
    }

    Component.onCompleted: backend.loadHome()
}
