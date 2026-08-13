import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

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

    background: Rectangle { color: Theme.canvas }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Metrics.pageMargin(root.width)
        spacing: Metrics.space4

        RowLayout {
            Layout.fillWidth: true
            Label { text: "下载"; color: Theme.textPrimary; font.pixelSize: Typography.pageTitle; font.weight: Typography.semibold }
            StatusBadge { text: backend.downloads.length + " 项"; status: "" }
            Item { Layout.fillWidth: true }
            IconButton { iconName: "refresh-cw"; tooltip: "刷新下载任务"; enabled: !(backend.activities.downloadsLoading || false); onClicked: backend.loadDownloads() }
        }
        Label {
            Layout.fillWidth: true
            text: "手动下载任务会持续同步 qBittorrent，下载内容直接保存在媒体库并关联 Episode。"
            color: Theme.textTertiary
            wrapMode: Text.Wrap
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: Metrics.space2
                Repeater {
                    model: backend.downloads
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 104
                        radius: Metrics.radiusS
                        color: downloadHover.hovered ? Theme.surfaceHover : Theme.surface
                        border.width: 1
                        border.color: downloadHover.hovered ? Theme.border : Theme.borderSoft
                        HoverHandler { id: downloadHover }
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: Metrics.space4
                            spacing: Metrics.space3
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: (modelData.subject ? modelData.subject.name : "条目已删除") + " · "
                                        + (modelData.episodes || []).map(item => "EP " + item.display_number).join(", ")
                                    color: Theme.textPrimary
                                    font.pixelSize: Typography.itemTitle
                                    elide: Text.ElideRight
                                    MouseArea { anchors.fill: parent; onClicked: if (modelData.subject) root.openSubject(modelData.subject.id) }
                                }
                                AppProgressBar { Layout.fillWidth: true; value: modelData.progress || 0 }
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.state + "  ·  " + Math.round((modelData.progress || 0) * 100) + "%"
                                        + (modelData.error ? "  ·  " + modelData.error : "")
                                    color: modelData.state === "FAILED" ? Theme.danger : Theme.textTertiary
                                    font.pixelSize: Typography.meta
                                    elide: Text.ElideRight
                                }
                            }
                            AppButton {
                                text: "暂停"
                                visible: ["QUEUED", "DOWNLOADING"].indexOf(modelData.state) >= 0
                                enabled: !(backend.activities.downloadMutating || false)
                                onClicked: backend.pauseDownload(modelData.id)
                            }
                            AppButton {
                                text: "继续"
                                visible: modelData.state === "STALLED"
                                enabled: !(backend.activities.downloadMutating || false)
                                onClicked: backend.resumeDownload(modelData.id)
                            }
                            AppButton {
                                text: "重试"
                                visible: modelData.state === "FAILED"
                                enabled: !(backend.activities.downloadMutating || false)
                                onClicked: backend.retryDownload(modelData.id)
                            }
                            IconButton {
                                iconName: "trash-2"
                                tooltip: "删除任务"
                                visible: modelData.state !== "IMPORTING"
                                enabled: !(backend.activities.downloadMutating || false)
                                onClicked: {
                                    root.pendingDeleteJob = modelData
                                    deleteDialog.open()
                                }
                            }
                        }
                    }
                }
                EmptyState { visible: backend.downloads.length === 0 && !(backend.activities.downloadsLoading || false); Layout.fillWidth: true; Layout.topMargin: Metrics.space16; title: "暂无下载任务"; detail: "从 Episode 资源候选或磁力链接创建下载。"; iconName: "download" }
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
            spacing: Metrics.space3
            Label {
                Layout.fillWidth: true
                text: root.pendingDeleteJob
                    ? "请选择如何删除“" + (root.pendingDeleteJob.subject ? root.pendingDeleteJob.subject.name : "未知条目") + "”的下载任务。"
                    : ""
                color: Theme.textPrimary
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: "删除任务及本地文件会删除对应媒体文件，已导入的 Episode 将无法播放，且无法撤销。"
                color: Theme.danger
                wrapMode: Text.Wrap
            }
        }

        footer: Pane {
            contentItem: RowLayout {
            spacing: Metrics.space3
                AppButton {
                    text: "取消"
                    onClicked: deleteDialog.close()
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    text: "仅删除下载任务"
                    onClicked: root.confirmDelete(false)
                }
                AppButton {
                    text: "删除任务及本地文件"
                    variant: "danger"
                    onClicked: root.confirmDelete(true)
                }
            }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: (backend.activities.downloadsLoading || false) && backend.downloads.length === 0 }
    Component.onCompleted: backend.setDownloadPolling("downloadsPage", visible)
    onVisibleChanged: backend.setDownloadPolling("downloadsPage", visible)
    Component.onDestruction: backend.setDownloadPolling("downloadsPage", false)
}
