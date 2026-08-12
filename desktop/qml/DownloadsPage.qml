import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    signal openSubject(int id)
    property var pendingDeleteJob: null

    function confirmDelete(deleteFiles) {
        if (!pendingDeleteJob)
            return
        const jobId = pendingDeleteJob.id
        deleteDialog.close()
        pendingDeleteJob = null
        backend.deleteDownload(jobId, deleteFiles)
    }

    background: Rectangle { color: "#0b1018" }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 30
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            Label { text: "下载"; color: "#f2f5f8"; font.pixelSize: 30; font.weight: Font.DemiBold }
            Item { Layout.fillWidth: true }
            Button { text: "刷新"; onClicked: backend.loadDownloads() }
        }
        Label {
            Layout.fillWidth: true
            text: "手动下载任务会持续同步 qBittorrent，下载内容直接保存在媒体库并关联 Episode。"
            color: "#93a1b2"
            wrapMode: Text.Wrap
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: 10
                Repeater {
                    model: backend.downloads
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 104
                        radius: 8
                        color: "#121a25"
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 14
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: (modelData.subject ? modelData.subject.name : "条目已删除") + " · "
                                        + (modelData.episodes || []).map(item => "EP " + item.display_number).join(", ")
                                    color: "#f2f5f8"
                                    font.pixelSize: 16
                                    elide: Text.ElideRight
                                    MouseArea { anchors.fill: parent; onClicked: if (modelData.subject) root.openSubject(modelData.subject.id) }
                                }
                                ProgressBar { Layout.fillWidth: true; value: modelData.progress || 0 }
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.state + "  ·  " + Math.round((modelData.progress || 0) * 100) + "%"
                                        + (modelData.error ? "  ·  " + modelData.error : "")
                                    color: modelData.state === "FAILED" ? "#ff9b9b" : "#93a1b2"
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                            }
                            Button {
                                text: "暂停"
                                visible: ["QUEUED", "DOWNLOADING"].indexOf(modelData.state) >= 0
                                onClicked: backend.pauseDownload(modelData.id)
                            }
                            Button {
                                text: "继续"
                                visible: modelData.state === "STALLED"
                                onClicked: backend.resumeDownload(modelData.id)
                            }
                            Button {
                                text: "重试"
                                visible: modelData.state === "FAILED"
                                onClicked: backend.retryDownload(modelData.id)
                            }
                            Button {
                                text: "删除任务"
                                flat: true
                                visible: modelData.state !== "IMPORTING"
                                onClicked: {
                                    root.pendingDeleteJob = modelData
                                    deleteDialog.open()
                                }
                            }
                        }
                    }
                }
                Label { visible: backend.downloads.length === 0 && !backend.busy; text: "暂无下载任务"; color: "#93a1b2" }
            }
        }
    }
    Dialog {
        id: deleteDialog
        anchors.centerIn: parent
        width: Math.min(620, root.width - 60)
        modal: true
        title: "确认删除下载任务"
        closePolicy: Popup.CloseOnEscape
        onClosed: root.pendingDeleteJob = null

        contentItem: ColumnLayout {
            spacing: 12
            Label {
                Layout.fillWidth: true
                text: root.pendingDeleteJob
                    ? "请选择如何删除“" + (root.pendingDeleteJob.subject ? root.pendingDeleteJob.subject.name : "未知条目") + "”的下载任务。"
                    : ""
                color: "#f2f5f8"
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: "删除任务及本地文件会删除对应媒体文件，已导入的 Episode 将无法播放，且无法撤销。"
                color: "#ffb4a8"
                wrapMode: Text.Wrap
            }
        }

        footer: Pane {
            contentItem: RowLayout {
                spacing: 10
                Button {
                    text: "取消"
                    onClicked: deleteDialog.close()
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "仅删除下载任务"
                    onClicked: root.confirmDelete(false)
                }
                Button {
                    text: "删除任务及本地文件"
                    highlighted: true
                    onClicked: root.confirmDelete(true)
                }
            }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy && backend.downloads.length === 0 }
    Component.onCompleted: backend.setDownloadPolling(true)
    onVisibleChanged: backend.setDownloadPolling(visible)
}
