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
                Button { text: "手动同步"; onClicked: backend.startBangumiSync() }
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
                    autoPlay.checked, writeback.checked
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
            username.text = bangumi.username || ""
            const values = storage.library_roots || (storage.library_path ? [storage.library_path] : ["data/library"])
            roots.text = values.join("\n")
            autoPlay.checked = playerSettings.auto_play_next || false
            writeback.checked = playerSettings.bangumi_writeback_enabled || false
            qbBaseUrl.text = qbittorrent.base_url || "http://127.0.0.1:8080"
            qbUsername.text = qbittorrent.username || ""
            qbPassword.text = ""
            token.text = ""
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: backend.busy }
    Component.onCompleted: backend.loadSettings()
}
