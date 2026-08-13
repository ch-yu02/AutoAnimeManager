import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    signal openSubject(int subjectId)
    property bool showHistory: false
    property var pendingDeleteRecord: null
    background: Rectangle { color: "#0b1018" }

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
        anchors.margins: 30
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: "隔离区"
                color: "#f2f5f8"
                font.pixelSize: 30
                font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "刷新"
                enabled: !backend.busy
                onClicked: backend.loadCleanupRecords()
            }
        }

        Label {
            Layout.fillWidth: true
            text: "隔离中的文件可恢复到原路径，也可在二次确认后立即永久删除。"
            color: "#93a1b2"
            wrapMode: Text.Wrap
        }

        ButtonGroup { id: viewGroup }
        RowLayout {
            RadioButton {
                text: "隔离中"
                checked: true
                ButtonGroup.group: viewGroup
                onCheckedChanged: if (checked) root.showHistory = false
            }
            RadioButton {
                text: "历史记录"
                ButtonGroup.group: viewGroup
                onCheckedChanged: if (checked) root.showHistory = true
            }
            Item { Layout.fillWidth: true }
            Label {
                text: root.visibleRecords().length + " 项"
                color: "#93a1b2"
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: 12

                Label {
                    Layout.fillWidth: true
                    visible: root.visibleRecords().length === 0
                    text: root.showHistory ? "暂无隔离历史" : "隔离区为空"
                    color: "#93a1b2"
                    font.pixelSize: 16
                    horizontalAlignment: Text.AlignHCenter
                    topPadding: 60
                }

                Repeater {
                    model: root.visibleRecords()
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: recordContent.implicitHeight + 28
                        color: "#121a25"
                        border.color: "#283445"
                        radius: 10

                        ColumnLayout {
                            id: recordContent
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.subject_name || ("Subject " + modelData.subject_id)
                                    color: "#f2f5f8"
                                    font.pixelSize: 18
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Label {
                                    text: root.statusText(modelData.status)
                                    color: modelData.status === "QUARANTINED" ? "#ffd166" : "#93a1b2"
                                }
                            }

                            Label {
                                Layout.fillWidth: true
                                text: root.formatBytes(modelData.bytes_total)
                                    + " · " + (modelData.files || []).length + " 个文件"
                                    + " · 隔离于 " + root.formatTime(modelData.quarantined_at)
                                    + (modelData.status === "QUARANTINED"
                                        ? " · 自动删除时间 " + root.formatTime(modelData.delete_after)
                                        : "")
                                color: "#93a1b2"
                                wrapMode: Text.Wrap
                            }

                            Label {
                                Layout.fillWidth: true
                                visible: (modelData.reasons || []).length > 0
                                text: (modelData.reasons || []).join("；")
                                color: "#b9c4d0"
                                wrapMode: Text.Wrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Button {
                                    text: "查看条目"
                                    onClicked: root.openSubject(modelData.subject_id)
                                }
                                Item { Layout.fillWidth: true }
                                Button {
                                    visible: modelData.status === "QUARANTINED"
                                    text: "恢复到原路径"
                                    enabled: !backend.busy
                                    onClicked: backend.restoreCleanup(modelData.id)
                                }
                                Button {
                                    visible: modelData.status === "QUARANTINED"
                                    text: "永久删除"
                                    enabled: !backend.busy
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

    BusyIndicator { anchors.centerIn: parent; running: backend.busy }

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
            color: "#f2f5f8"
            wrapMode: Text.Wrap
        }
    }

    Component.onCompleted: backend.loadCleanupRecords()
}
