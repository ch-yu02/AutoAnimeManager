import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import AutoAnime 1.0

Page {
    id: root
    objectName: "playerPage"
    required property int requestedEpisodeId
    required property bool fromStart
    required property var episodeModel
    required property string subjectTitle
    signal back()
    property bool controlsVisible: true
    property bool seeking: false
    property int currentIndex: {
        for (let i = 0; i < episodeModel.length; ++i)
            if (episodeModel[i].id === player.episodeId || episodeModel[i].id === requestedEpisodeId) return i
        return -1
    }

    function formatTime(seconds) {
        const value = Math.max(0, Math.floor(seconds || 0))
        const h = Math.floor(value / 3600)
        const m = Math.floor((value % 3600) / 60)
        const s = value % 60
        return h > 0 ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0") : m + ":" + String(s).padStart(2, "0")
    }
    function playAdjacent(offset) {
        const index = currentIndex + offset
        if (index >= 0 && index < episodeModel.length && episodeModel[index].local_status === "READY")
            player.play(episodeModel[index].id, false)
    }
    function toggleFullscreen() {
        if (ApplicationWindow.window.visibility === Window.FullScreen) ApplicationWindow.window.showNormal()
        else ApplicationWindow.window.showFullScreen()
    }

    background: Rectangle { color: "black" }
    MpvVideoItem { anchors.fill: parent }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onPositionChanged: { root.controlsVisible = true; hideTimer.restart() }
        onClicked: player.togglePause()
        onDoubleClicked: root.toggleFullscreen()
    }

    Rectangle {
        anchors.fill: parent
        visible: player.loading
        color: "#66000000"
        BusyIndicator { anchors.centerIn: parent; running: true }
    }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 70
        visible: root.controlsVisible
        gradient: Gradient { GradientStop { position: 0; color: "#bb000000" } GradientStop { position: 1; color: "transparent" } }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18
            Button { text: "‹"; flat: true; font.pixelSize: 24; onClicked: { player.stop(); root.back() } }
            Label { Layout.fillWidth: true; text: root.subjectTitle; color: "white"; font.pixelSize: 17; elide: Text.ElideRight }
            Label { text: "HW: " + (player.hwdec || "software") + "  掉帧: " + player.droppedFrames; color: "#bdc6d2"; font.pixelSize: 12 }
        }
    }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 112
        visible: root.controlsVisible
        gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: "#dd000000" } }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 14; spacing: 4
            Slider {
                id: timeline
                Layout.fillWidth: true
                from: 0; to: Math.max(1, player.duration)
                value: 0
                onPressedChanged: {
                    root.seeking = pressed
                    if (!pressed) player.seek(value)
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "◀"; flat: true; enabled: root.currentIndex > 0; onClicked: root.playAdjacent(-1) }
                Button { text: player.paused ? "▶" : "Ⅱ"; flat: true; font.pixelSize: 20; onClicked: player.togglePause() }
                Button { text: "▶|"; flat: true; enabled: root.currentIndex >= 0 && root.currentIndex + 1 < root.episodeModel.length; onClicked: root.playAdjacent(1) }
                Label { text: root.formatTime(root.seeking ? timeline.value : player.position) + " / " + root.formatTime(player.duration); color: "white" }
                Item { Layout.fillWidth: true }
                Button { text: player.muted ? "静音" : "音量"; flat: true; onClicked: player.toggleMute() }
                Slider { Layout.preferredWidth: 110; from: 0; to: 100; value: player.volume; onMoved: player.setVolume(value) }
                Button { text: player.speed.toFixed(2) + "×"; flat: true; onClicked: speedMenu.open(); Menu { id: speedMenu; Repeater { model: [0.5, 0.75, 1, 1.25, 1.5, 2]; delegate: MenuItem { required property var modelData; text: modelData + "×"; onTriggered: player.setSpeed(modelData) } } } }
                Button { text: "音轨"; flat: true; onClicked: audioMenu.open(); Menu { id: audioMenu; Repeater { model: player.audioTracks; delegate: MenuItem { required property var modelData; text: (modelData.selected ? "✓ " : "") + modelData.label; onTriggered: player.selectAudioTrack(modelData.id) } } } }
                Button { text: "字幕"; flat: true; onClicked: subtitleMenu.open(); Menu { id: subtitleMenu; MenuItem { text: "关闭字幕"; onTriggered: player.selectSubtitleTrack(-1) } Repeater { model: player.subtitleTracks; delegate: MenuItem { required property var modelData; text: (modelData.selected ? "✓ " : "") + modelData.label; onTriggered: player.selectSubtitleTrack(modelData.id) } } MenuSeparator {} MenuItem { text: "加载外挂字幕…"; onTriggered: subtitleDialog.open() } } }
                Button { text: "⛶"; flat: true; font.pixelSize: 20; onClicked: root.toggleFullscreen() }
            }
        }
    }

    Rectangle {
        visible: player.error.length > 0
        anchors.centerIn: parent
        width: Math.min(errorLabel.implicitWidth + 40, parent.width - 80)
        height: errorLabel.implicitHeight + 30
        radius: 8; color: "#bb782d3d"
        Label { id: errorLabel; anchors.centerIn: parent; text: player.error; color: "white"; wrapMode: Text.Wrap }
    }

    Timer { id: hideTimer; interval: 2500; onTriggered: root.controlsVisible = false }
    FileDialog { id: subtitleDialog; title: "选择字幕"; nameFilters: ["字幕文件 (*.ass *.ssa *.srt *.vtt *.sup)", "所有文件 (*)"]; onAccepted: player.addSubtitle(selectedFile) }
    Shortcut { sequence: "Space"; onActivated: player.togglePause() }
    Shortcut { sequence: "Left"; onActivated: player.seekRelative(-5) }
    Shortcut { sequence: "Right"; onActivated: player.seekRelative(5) }
    Shortcut { sequence: "Up"; onActivated: player.setVolume(Math.min(100, player.volume + 5)) }
    Shortcut { sequence: "Down"; onActivated: player.setVolume(Math.max(0, player.volume - 5)) }
    Shortcut { sequence: "M"; onActivated: player.toggleMute() }
    Shortcut { sequence: "F"; onActivated: root.toggleFullscreen() }
    Shortcut { sequence: "Escape"; onActivated: { if (ApplicationWindow.window.visibility === Window.FullScreen) ApplicationWindow.window.showNormal(); else { player.stop(); root.back() } } }
    Shortcut { sequence: "Ctrl+O"; onActivated: subtitleDialog.open() }

    Connections {
        target: player
        function onPositionChanged() {
            if (!timeline.pressed) timeline.value = player.position
        }
        function onPlaybackEnded(episodeId, nextEpisodeId) {
            const settingsPlayer = backend.settings.player || {}
            if (settingsPlayer.auto_play_next && nextEpisodeId > 0) player.play(nextEpisodeId, false)
        }
    }
    Component.onCompleted: { hideTimer.start(); player.play(requestedEpisodeId, fromStart) }
}
