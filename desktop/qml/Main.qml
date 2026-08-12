import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material

ApplicationWindow {
    id: window
    width: 1360
    height: 820
    minimumWidth: 900
    minimumHeight: 600
    visible: true
    title: "AutoAnime"
    color: "#0b1018"
    Material.theme: Material.Dark
    Material.accent: accentColor
    Material.primary: "#1a2938"
    Material.background: "#0b1018"
    Material.foreground: textColor

    palette.window: "#0b1018"
    palette.windowText: textColor
    palette.base: "#111a25"
    palette.alternateBase: "#172231"
    palette.text: textColor
    palette.button: "#243244"
    palette.buttonText: textColor
    palette.brightText: "#ffffff"
    palette.highlight: accentColor
    palette.highlightedText: "#07130f"
    palette.placeholderText: "#8190a3"
    palette.toolTipBase: "#243244"
    palette.toolTipText: "#ffffff"

    property color panelColor: "#121a25"
    property color panelHover: "#1a2635"
    property color textColor: "#f2f5f8"
    property color mutedColor: "#93a1b2"
    property color accentColor: "#72d5b4"
    property bool playerOpen: stack.currentItem && stack.currentItem.objectName === "playerPage"

    function leavePlayer() { if (playerOpen) player.stop() }
    function openHome() { leavePlayer(); stack.replace(homeComponent) }
    function openSubjects() { leavePlayer(); stack.replace(subjectsComponent) }
    function openSubject(id) { leavePlayer(); stack.replace(detailComponent, { subjectId: id }) }
    function openLibrary() { leavePlayer(); stack.replace(libraryComponent) }
    function openDownloads() { leavePlayer(); stack.replace(downloadsComponent) }
    function openSettings() { leavePlayer(); stack.replace(settingsComponent) }
    function openPlayer(episodeId, fromStart, episodes, title) {
        stack.push(playerComponent, {
            requestedEpisodeId: episodeId,
            fromStart: fromStart,
            episodeModel: episodes || [],
            subjectTitle: title || ""
        })
    }

    Shortcut { sequence: "Ctrl+1"; onActivated: window.openHome() }
    Shortcut { sequence: "Ctrl+2"; onActivated: window.openSubjects() }
    Shortcut { sequence: "Ctrl+3"; onActivated: window.openLibrary() }
    Shortcut { sequence: "Ctrl+4"; onActivated: window.openDownloads() }
    Shortcut { sequence: "Ctrl+,"; onActivated: window.openSettings() }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: window.playerOpen ? 0 : 210
            Layout.fillHeight: true
            color: "#0e151f"
            visible: !window.playerOpen
            clip: true

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 8

                Label {
                    text: "AutoAnime"
                    color: window.textColor
                    font.pixelSize: 24
                    font.weight: Font.DemiBold
                    Layout.bottomMargin: 22
                }
                Repeater {
                    model: [
                        { label: "首页", icon: "⌂", action: window.openHome },
                        { label: "条目", icon: "▦", action: window.openSubjects },
                        { label: "媒体库", icon: "◫", action: window.openLibrary },
                        { label: "下载", icon: "⇩", action: window.openDownloads },
                        { label: "设置", icon: "⚙", action: window.openSettings }
                    ]
                    delegate: Button {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData.icon + "   " + modelData.label
                        flat: true
                        font.pixelSize: 15
                        onClicked: modelData.action()
                        contentItem: Label {
                            text: parent.text
                            color: parent.hovered ? window.accentColor : window.textColor
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            color: parent.hovered ? window.panelHover : "transparent"
                            radius: 8
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                Label {
                    text: backend.status.version ? "Core " + backend.status.version : "本地原生客户端"
                    color: window.mutedColor
                    font.pixelSize: 12
                }
            }
        }

        StackView {
            id: stack
            Layout.fillWidth: true
            Layout.fillHeight: true
            initialItem: homeComponent
            clip: true
        }
    }

    Rectangle {
        visible: backend.error.length > 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        width: Math.min(errorText.implicitWidth + 76, parent.width - 48)
        height: Math.max(48, errorText.implicitHeight + 24)
        radius: 8
        color: "#822f3f"
        z: 100
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 8
            Label { id: errorText; Layout.fillWidth: true; text: backend.error; color: "white"; wrapMode: Text.Wrap }
            Button {
                text: "×"
                flat: true
                onClicked: backend.dismissError()
                contentItem: Label { text: parent.text; color: "white"; font.pixelSize: 20; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }

    Rectangle {
        visible: backend.notice.length > 0 && backend.error.length === 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        width: Math.min(noticeText.implicitWidth + 76, parent.width - 48)
        height: Math.max(48, noticeText.implicitHeight + 24)
        radius: 8
        color: "#245f52"
        z: 99
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 8
            Label { id: noticeText; Layout.fillWidth: true; text: backend.notice; color: "white"; wrapMode: Text.Wrap }
            Button {
                text: "×"
                flat: true
                onClicked: backend.dismissNotice()
                contentItem: Label { text: parent.text; color: "white"; font.pixelSize: 20; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }

    Timer {
        id: noticeTimer
        interval: 4000
        onTriggered: backend.dismissNotice()
    }
    Connections {
        target: backend
        function onNoticeChanged() {
            if (backend.notice.length > 0) noticeTimer.restart()
            else noticeTimer.stop()
        }
    }

    Component { id: homeComponent; HomePage { onOpenSubject: id => window.openSubject(id); onPlayEpisode: (id, title) => window.openPlayer(id, false, [], title) } }
    Component { id: subjectsComponent; SubjectsPage { onOpenSubject: id => window.openSubject(id) } }
    Component { id: detailComponent; SubjectDetailPage { onBack: window.openSubjects(); onPlayEpisode: (id, fromStart, episodes, title) => window.openPlayer(id, fromStart, episodes, title) } }
    Component { id: playerComponent; PlayerPage { onBack: stack.pop() } }
    Component { id: libraryComponent; LibraryPage {} }
    Component { id: downloadsComponent; DownloadsPage { onOpenSubject: id => window.openSubject(id) } }
    Component { id: settingsComponent; SettingsPage {} }

    Component.onCompleted: {
        backend.loadSettings()
        if (startupEpisodeId > 0) openPlayer(startupEpisodeId, false, [], "播放性能验收")
    }
}
