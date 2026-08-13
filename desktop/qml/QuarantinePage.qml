import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    signal openSubject(int subjectId)
    property bool showHistory: false
    property var pendingDeleteRecord: null
    background: Rectangle { color: Theme.canvas }

    function visibleRecords() {
        const records = backend.cleanupRecords || []
        return records.filter(item => root.showHistory
            ? item.status !== "QUARANTINED"
            : item.status === "QUARANTINED")
    }

    function formatBytes(bytes) {
        const value = Number(bytes || 0)
        if (value < 1024 * 1024) return Math.round(value / 1024) + " KiB"
        if (value < 1024 * 1024 * 1024) return (value / 1024 / 1024).toFixed(1) + " MiB"
        return (value / 1024 / 1024 / 1024).toFixed(1) + " GiB"
    }

    function formatTime(value) {
        if (!value) return "未知"
        const parsed = new Date(value)
        return isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString(Qt.locale())
    }

    function statusText(status) {
        if (status === "QUARANTINED") return "隔离中"
        if (status === "RESTORED") return "已恢复"
        if (status === "DELETED") return "已永久删除"
        return status || "未知"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Metrics.pageMargin(root.width)
        spacing: Metrics.space4

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: "隔离区"
                color: Theme.textPrimary
                font.pixelSize: Typography.pageTitle
                font.weight: Typography.semibold
            }
            Item { Layout.fillWidth: true }
            IconButton {
                iconName: "refresh-cw"
                tooltip: "刷新隔离区"
                enabled: !(backend.activities.cleanupRecordsLoading || false)
                onClicked: backend.loadCleanupRecords()
            }
        }

        Label {
            Layout.fillWidth: true
            text: "隔离中的文件可恢复到原路径，也可在二次确认后立即永久删除。"
            color: Theme.textTertiary
            wrapMode: Text.Wrap
        }

        ButtonGroup { id: viewGroup }
        RowLayout {
            AppTab {
                text: "隔离中"
                checked: true
                ButtonGroup.group: viewGroup
                onCheckedChanged: if (checked) root.showHistory = false
            }
            AppTab {
                text: "历史记录"
                ButtonGroup.group: viewGroup
                onCheckedChanged: if (checked) root.showHistory = true
            }
            Item { Layout.fillWidth: true }
            Label {
                text: root.visibleRecords().length + " 项"
                color: Theme.textTertiary
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: Metrics.space3

                EmptyState {
                    Layout.fillWidth: true
                    visible: root.visibleRecords().length === 0 && !(backend.activities.cleanupRecordsLoading || false)
                    title: root.showHistory ? "暂无隔离历史" : "隔离区为空"
                    detail: root.showHistory ? "恢复和永久删除记录会显示在这里。" : "当前没有等待处理的隔离文件。"
                    iconName: "archive-restore"
                    Layout.topMargin: Metrics.space16
                }

                Repeater {
                    model: root.visibleRecords()
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: recordContent.implicitHeight + 28
                        color: quarantineHover.hovered ? Theme.surfaceHover : Theme.surface
                        border.color: quarantineHover.hovered ? Theme.border : Theme.borderSoft
                        radius: Metrics.radiusM
                        HoverHandler { id: quarantineHover }

                        ColumnLayout {
                            id: recordContent
                            anchors.fill: parent
                            anchors.margins: Metrics.space4
                            spacing: Metrics.space2

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.subject_name || ("Subject " + modelData.subject_id)
                                    color: Theme.textPrimary
                                    font.pixelSize: Typography.itemTitle
                                    font.weight: Typography.semibold
                                    elide: Text.ElideRight
                                }
                                StatusBadge { text: root.statusText(modelData.status); status: modelData.status }
                            }

                            Label {
                                Layout.fillWidth: true
                                text: root.formatBytes(modelData.bytes_total)
                                    + " · " + (modelData.files || []).length + " 个文件"
                                    + " · 隔离于 " + root.formatTime(modelData.quarantined_at)
                                    + (modelData.status === "QUARANTINED"
                                        ? " · 自动删除时间 " + root.formatTime(modelData.delete_after)
                                        : "")
                                color: Theme.textTertiary
                                wrapMode: Text.Wrap
                            }

                            Label {
                                Layout.fillWidth: true
                                visible: (modelData.reasons || []).length > 0
                                text: (modelData.reasons || []).join("；")
                                color: Theme.textSecondary
                                wrapMode: Text.Wrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                AppButton {
                                    text: "查看条目"
                                    onClicked: root.openSubject(modelData.subject_id)
                                }
                                Item { Layout.fillWidth: true }
                                AppButton {
                                    variant: "primary"
                                    visible: modelData.status === "QUARANTINED"
                                    text: "恢复到原路径"
                                    enabled: !(backend.activities.cleanupMutating || false)
                                    onClicked: backend.restoreCleanup(modelData.id)
                                }
                                AppButton {
                                    variant: "danger"
                                    visible: modelData.status === "QUARANTINED"
                                    text: "永久删除"
                                    enabled: !(backend.activities.cleanupMutating || false)
                                    onClicked: {
                                        root.pendingDeleteRecord = modelData
                                        permanentDeleteDialog.open()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    BusyIndicator { anchors.centerIn: parent; running: (backend.activities.cleanupRecordsLoading || false) && backend.cleanupRecords.length === 0 }

    Dialog {
        id: permanentDeleteDialog
        anchors.centerIn: parent
        modal: true
        title: "永久删除媒体文件"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            if (root.pendingDeleteRecord)
                backend.permanentlyDeleteCleanup(root.pendingDeleteRecord.id)
            root.pendingDeleteRecord = null
        }
        onRejected: root.pendingDeleteRecord = null
        contentItem: Label {
            text: root.pendingDeleteRecord
                ? "将永久删除“" + root.pendingDeleteRecord.subject_name
                    + "”的 " + (root.pendingDeleteRecord.files || []).length
                    + " 个隔离文件（" + root.formatBytes(root.pendingDeleteRecord.bytes_total)
                    + "）。此操作不可恢复。"
                : ""
            color: Theme.textPrimary
            wrapMode: Text.Wrap
        }
    }

    Component.onCompleted: backend.loadCleanupRecords()
}
