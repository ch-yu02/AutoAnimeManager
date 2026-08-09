import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    required property int subjectId
    signal back()
    signal playEpisode(int id, bool fromStart, var episodes, string title)
    background: Rectangle { color: "#0b1018" }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 22
            anchors.margins: 30

            Button { text: "‹ 返回条目"; flat: true; onClicked: root.back() }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 300
                spacing: 28
                Image {
                    Layout.preferredWidth: 200; Layout.fillHeight: true
                    source: backend.subject.image_url || ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Label { Layout.fillWidth: true; text: backend.subject.display_name || "加载中…"; color: "#f2f5f8"; font.pixelSize: 32; font.weight: Font.Bold; wrapMode: Text.Wrap }
                    Label { text: (backend.subject.air_date || "日期未知") + "  ·  " + (backend.subject.platform || "平台未知"); color: "#93a1b2" }
                    Label { Layout.fillWidth: true; Layout.fillHeight: true; text: backend.subject.summary || "暂无简介"; color: "#c8d0da"; wrapMode: Text.Wrap; maximumLineCount: 8; elide: Text.ElideRight }
                    Button {
                        property var readyEpisode: {
                            for (let i = 0; i < backend.episodes.length; ++i)
                                if (backend.episodes[i].local_status === "READY" && !backend.episodes[i].watched) return backend.episodes[i]
                            for (let j = 0; j < backend.episodes.length; ++j)
                                if (backend.episodes[j].local_status === "READY") return backend.episodes[j]
                            return null
                        }
                        text: readyEpisode && readyEpisode.playback && readyEpisode.playback.position_seconds > 0 ? "继续观看" : "播放"
                        highlighted: true
                        enabled: readyEpisode !== null
                        onClicked: root.playEpisode(readyEpisode.id, false, backend.episodes, backend.subject.display_name)
                    }
                }
            }
            Label { text: "剧集"; color: "#f2f5f8"; font.pixelSize: 22; font.weight: Font.DemiBold }
            Label {
                visible: (backend.subject.relations || []).length > 0
                Layout.fillWidth: true
                text: "相关条目：" + (backend.subject.relations || []).map(item => (item.name_cn || item.name) + "（" + item.relation_type + "）").join(" · ")
                color: "#93a1b2"
                wrapMode: Text.Wrap
            }
            Repeater {
                model: backend.episodes
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 68
                    radius: 8
                    color: "#121a25"
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 14
                        Label { text: modelData.episode_type + " " + modelData.display_number; color: "#72d5b4"; Layout.preferredWidth: 90 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 3
                            Label { Layout.fillWidth: true; text: modelData.name_cn || modelData.name || "未命名"; color: "#f2f5f8"; elide: Text.ElideRight }
                            Label { text: (modelData.air_date || "日期未知") + "  ·  " + modelData.local_status; color: "#93a1b2"; font.pixelSize: 12 }
                        }
                        ProgressBar { Layout.preferredWidth: 110; visible: modelData.playback !== null && modelData.playback !== undefined; value: modelData.playback ? modelData.playback.progress_ratio : 0 }
                        Button { text: modelData.watched ? "设为未看" : "设为已看"; flat: true; onClicked: backend.markWatched(modelData.id, !modelData.watched) }
                        Button { text: modelData.playback && modelData.playback.position_seconds > 0 ? "继续" : "播放"; enabled: modelData.local_status === "READY"; onClicked: root.playEpisode(modelData.id, false, backend.episodes, backend.subject.display_name) }
                        Button { text: "从头"; enabled: modelData.local_status === "READY"; flat: true; onClicked: root.playEpisode(modelData.id, true, backend.episodes, backend.subject.display_name) }
                    }
                }
            }
            Label { visible: backend.episodes.length === 0 && !backend.busy; text: "暂无章节数据"; color: "#93a1b2" }
            Item { Layout.preferredHeight: 24 }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy && backend.subject.id !== subjectId }
    Component.onCompleted: backend.loadSubject(subjectId)
}
