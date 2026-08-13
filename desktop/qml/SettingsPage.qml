import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    property var config: backend.settings
    background: Rectangle { color: "#0b1018" }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            width: Math.min(parent.width, 900)
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.margins: 30
            spacing: 18

            Label { text: "设置"; color: "#f2f5f8"; font.pixelSize: 30; font.weight: Font.DemiBold }
            Label { text: "Bangumi"; color: "#f2f5f8"; font.pixelSize: 20; font.weight: Font.DemiBold }
            TextField { id: username; Layout.fillWidth: true; placeholderText: "Bangumi 用户名" }
            TextField { id: token; Layout.fillWidth: true; placeholderText: "Access Token（留空表示保留）"; echoMode: TextInput.Password }
            RowLayout {
                Button { text: "测试 Bangumi"; onClicked: backend.testConnection("bangumi") }
                Button { text: "完整同步"; onClicked: backend.startBangumiSync() }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#283445" }
            Label { text: "qBittorrent"; color: "#f2f5f8"; font.pixelSize: 20; font.weight: Font.DemiBold }
            TextField { id: qbBaseUrl; Layout.fillWidth: true; placeholderText: "WebUI 地址，例如 http://127.0.0.1:8080" }
            TextField { id: qbUsername; Layout.fillWidth: true; placeholderText: "WebUI 用户名" }
            TextField { id: qbPassword; Layout.fillWidth: true; placeholderText: "WebUI 密码（留空表示保留）"; echoMode: TextInput.Password }
            Label {
                Layout.fillWidth: true
                text: "下载内容直接保存到第一个媒体目录下的 Subject 文件夹，不创建副本或 hardlink。"
                color: "#93a1b2"
                wrapMode: Text.Wrap
            }
            Button { text: "测试 qBittorrent"; onClicked: backend.testConnection("qbittorrent") }
            CheckBox {
                id: autoDownload
                text: "自动下载在看条目的已放送未看正片"
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#283445" }
            Label { text: "文件清理"; color: "#f2f5f8"; font.pixelSize: 20; font.weight: Font.DemiBold }
            CheckBox { id: cleanupEnabled; text: "启用自动隔离和到期永久删除" }
            RowLayout {
                Label { text: "看完后保留天数"; color: "#f2f5f8" }
                SpinBox { id: retentionDays; from: 0; to: 3650; value: 14 }
                Label { text: "隔离区保留天数"; color: "#f2f5f8" }
                SpinBox { id: quarantineDays; from: 1; to: 365; value: 7 }
            }
            Label {
                Layout.fillWidth: true
                text: "永久删除前会重新检查资格；Subject、Episode、观看历史、下载记录和清理日志不会删除。"
                color: "#93a1b2"
                wrapMode: Text.Wrap
            }
            Label { text: "自动任务"; color: "#f2f5f8"; font.pixelSize: 20; font.weight: Font.DemiBold }
            Label {
                Layout.fillWidth: true
                text: "任务失败会自动退避并在重启后恢复。手动执行不受定时间隔限制。"
                color: "#93a1b2"
                wrapMode: Text.Wrap
            }
            Repeater {
                model: (backend.scheduler.tasks || [])
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Label {
                        Layout.preferredWidth: 170
                        text: modelData.name
                        color: "#f2f5f8"
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.latest
                            ? modelData.latest.status + (modelData.latest.error ? " · " + modelData.latest.error : "")
                            : "尚未执行"
                        color: modelData.latest && modelData.latest.status === "FAILED" ? "#ff9f9f" : "#93a1b2"
                        elide: Text.ElideRight
                    }
                    Button {
                        text: modelData.active ? "运行中" : "立即执行"
                        enabled: !modelData.active && !backend.busy
                        onClicked: backend.runSchedulerTask(modelData.name)
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#283445" }
            Label { text: "媒体目录"; color: "#f2f5f8"; font.pixelSize: 20; font.weight: Font.DemiBold }
            TextArea { id: roots; Layout.fillWidth: true; Layout.preferredHeight: 100; placeholderText: "每行一个扫描目录"; wrapMode: TextEdit.NoWrap }
            RowLayout {
                Button { text: "测试 ffprobe"; onClicked: backend.testConnection("ffprobe") }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#283445" }
            Label { text: "播放"; color: "#f2f5f8"; font.pixelSize: 20; font.weight: Font.DemiBold }
            CheckBox { id: autoPlay; text: "播放完成后自动播放下一集" }
            CheckBox { id: writeback; text: "回写 Bangumi 已看状态" }
            Button {
                text: "保存设置"
                highlighted: true
                enabled: !backend.busy
                onClicked: backend.saveSettings(
                    username.text, token.text, roots.text,
                    qbBaseUrl.text, qbUsername.text, qbPassword.text,
                    autoPlay.checked, writeback.checked, autoDownload.checked,
                    cleanupEnabled.checked, retentionDays.value, quarantineDays.value
                )
            }
            Item { Layout.preferredHeight: 24 }
        }
    }

    Connections {
        target: backend
        function onSettingsChanged() {
            const bangumi = backend.settings.bangumi || {}
            const storage = backend.settings.storage || {}
            const playerSettings = backend.settings.player || {}
            const qbittorrent = backend.settings.qbittorrent || {}
            const scheduler = backend.settings.scheduler || {}
            const cleanup = backend.settings.cleanup || {}
            username.text = bangumi.username || ""
            const values = storage.library_roots || (storage.library_path ? [storage.library_path] : ["data/library"])
            roots.text = values.join("\n")
            autoPlay.checked = playerSettings.auto_play_next || false
            writeback.checked = playerSettings.bangumi_writeback_enabled || false
            autoDownload.checked = scheduler.auto_download_enabled || false
            cleanupEnabled.checked = cleanup.enabled || false
            retentionDays.value = cleanup.retention_days === undefined ? 14 : cleanup.retention_days
            quarantineDays.value = cleanup.quarantine_days === undefined ? 7 : cleanup.quarantine_days
            qbBaseUrl.text = qbittorrent.base_url || "http://127.0.0.1:8080"
            qbUsername.text = qbittorrent.username || ""
            qbPassword.text = ""
            token.text = ""
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy }
    Component.onCompleted: {
        backend.loadSettings()
        backend.loadScheduler()
    }
}
