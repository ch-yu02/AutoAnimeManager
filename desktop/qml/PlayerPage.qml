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
    function revealControls() { controlsVisible = true; hideTimer.restart() }
    function playAdjacent(offset) {
        const index = currentIndex + offset
        if (index >= 0 && index < episodeModel.length && episodeModel[index].local_status === "READY")
            player.play(episodeModel[index].id, false)
    }
    function toggleFullscreen() {
        if (ApplicationWindow.window.visibility === Window.FullScreen) ApplicationWindow.window.showNormal()
        else ApplicationWindow.window.showFullScreen()
    }

    background: Rectangle { color: Theme.screenBlack }
    MpvVideoItem { anchors.fill: parent }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onPositionChanged: root.revealControls()
        onClicked: { player.togglePause(); root.revealControls() }
        onDoubleClicked: root.toggleFullscreen()
    }

    Rectangle { anchors.fill: parent; visible: player.loading; color: Qt.rgba(0, 0, 0, 0.45); BusyIndicator { anchors.centerIn: parent; running: true } }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: Metrics.pageHeaderHeight
        visible: root.controlsVisible || player.paused
        gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0.82) } GradientStop { position: 1; color: "transparent" } }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Metrics.space4
            anchors.rightMargin: Metrics.space4
            IconButton { iconName: "arrow-left"; iconSize: 24; tooltip: "返回（Esc）"; onClicked: { player.stop(); root.back() } }
            Label { Layout.fillWidth: true; text: root.subjectTitle; color: Theme.textPrimary; font.pixelSize: Typography.itemTitle; font.weight: Typography.semibold; elide: Text.ElideRight }
            IconButton { iconName: "more-horizontal"; tooltip: "播放信息"; onClicked: infoMenu.open(); Menu { id: infoMenu; MenuItem { text: "硬件解码：" + (player.hwdec || "software"); enabled: false } MenuItem { text: "掉帧：" + player.droppedFrames; enabled: false } } }
        }
        Behavior on opacity { NumberAnimation { duration: 160 } }
    }

    AppButton {
        anchors.centerIn: parent
        visible: player.paused && !player.loading
        width: 64
        height: 64
        text: ""
        iconName: "play"
        variant: "primary"
        onClicked: { player.togglePause(); root.revealControls() }
    }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 120
        visible: root.controlsVisible || player.paused
        gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.88) } }
        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: Metrics.space4
            anchors.rightMargin: Metrics.space4
            anchors.bottomMargin: Metrics.space3
            spacing: Metrics.space1
            Slider {
                id: timeline
                Layout.fillWidth: true
                from: 0; to: Math.max(1, player.duration)
                value: 0
                onPressedChanged: {
                    root.seeking = pressed
                    if (!pressed) player.seek(value)
                    root.revealControls()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Metrics.space1
                IconButton { iconName: "skip-back"; iconSize: 24; tooltip: "上一集"; enabled: root.currentIndex > 0; onClicked: root.playAdjacent(-1) }
                IconButton { iconName: player.paused ? "play" : "pause"; iconSize: 24; tooltip: player.paused ? "播放（Space）" : "暂停（Space）"; onClicked: { player.togglePause(); root.revealControls() } }
                IconButton { iconName: "skip-forward"; iconSize: 24; tooltip: "下一集"; enabled: root.currentIndex >= 0 && root.currentIndex + 1 < root.episodeModel.length; onClicked: root.playAdjacent(1) }
                Label { text: root.formatTime(root.seeking ? timeline.value : player.position) + " / " + root.formatTime(player.duration); color: Theme.textPrimary; font.family: Typography.monoFamily; font.pixelSize: Typography.meta }
                Item { Layout.fillWidth: true }
                IconButton { iconName: player.muted ? "volume-x" : "volume-2"; tooltip: player.muted ? "取消静音（M）" : "静音（M）"; onClicked: player.toggleMute() }
                Slider { Layout.preferredWidth: 112; from: 0; to: 100; value: player.volume; onMoved: player.setVolume(value) }
                AppButton { text: player.speed.toFixed(2) + "×"; variant: "ghost"; onClicked: speedMenu.open(); Menu { id: speedMenu; Repeater { model: [0.5, 0.75, 1, 1.25, 1.5, 2]; delegate: MenuItem { required property var modelData; text: modelData + "×"; onTriggered: player.setSpeed(modelData) } } } }
                IconButton { iconName: "audio-lines"; tooltip: "音轨"; onClicked: audioMenu.open(); Menu { id: audioMenu; Repeater { model: player.audioTracks; delegate: MenuItem { required property var modelData; text: (modelData.selected ? "✓ " : "") + modelData.label; onTriggered: player.selectAudioTrack(modelData.id) } } } }
                IconButton { iconName: "captions"; tooltip: "字幕"; onClicked: subtitleMenu.open(); Menu { id: subtitleMenu; MenuItem { text: "关闭字幕"; onTriggered: player.selectSubtitleTrack(-1) } Repeater { model: player.subtitleTracks; delegate: MenuItem { required property var modelData; text: (modelData.selected ? "✓ " : "") + modelData.label; onTriggered: player.selectSubtitleTrack(modelData.id) } } MenuSeparator {} MenuItem { text: "加载外挂字幕…"; onTriggered: subtitleDialog.open() } } }
                IconButton { iconName: "maximize"; iconSize: 24; tooltip: "全屏（F）"; onClicked: root.toggleFullscreen() }
            }
        }
        Behavior on opacity { NumberAnimation { duration: 160 } }
    }

    Rectangle {
        visible: player.error.length > 0
        anchors.centerIn: parent
        width: Math.min(errorLabel.implicitWidth + Metrics.space12, parent.width - Metrics.space16)
        height: errorLabel.implicitHeight + Metrics.space8
        radius: Metrics.radiusM
        color: Theme.surfaceRaised
        border.width: 1
        border.color: Theme.danger
        Label { id: errorLabel; anchors.centerIn: parent; text: player.error; color: Theme.textPrimary; wrapMode: Text.Wrap }
    }

    Timer { id: hideTimer; interval: 2500; onTriggered: if (!player.paused) root.controlsVisible = false }
    FileDialog { id: subtitleDialog; title: "选择字幕"; nameFilters: ["字幕文件 (*.ass *.ssa *.srt *.vtt *.sup)", "所有文件 (*)"]; onAccepted: player.addSubtitle(selectedFile) }
    Shortcut { sequence: "Space"; onActivated: { player.togglePause(); root.revealControls() } }
    Shortcut { sequence: "Left"; onActivated: { player.seekRelative(-5); root.revealControls() } }
    Shortcut { sequence: "Right"; onActivated: { player.seekRelative(5); root.revealControls() } }
    Shortcut { sequence: "Up"; onActivated: { player.setVolume(Math.min(100, player.volume + 5)); root.revealControls() } }
    Shortcut { sequence: "Down"; onActivated: { player.setVolume(Math.max(0, player.volume - 5)); root.revealControls() } }
    Shortcut { sequence: "M"; onActivated: player.toggleMute() }
    Shortcut { sequence: "F"; onActivated: root.toggleFullscreen() }
    Shortcut { sequence: "Escape"; onActivated: { if (ApplicationWindow.window.visibility === Window.FullScreen) ApplicationWindow.window.showNormal(); else { player.stop(); root.back() } } }
    Shortcut { sequence: "Ctrl+O"; onActivated: subtitleDialog.open() }

    Connections {
        target: player
        function onPositionChanged() { if (!timeline.pressed) timeline.value = player.position }
        function onPlaybackEnded(episodeId, nextEpisodeId) {
            const settingsPlayer = backend.settings.player || {}
            if (settingsPlayer.auto_play_next && nextEpisodeId > 0) player.play(nextEpisodeId, false)
        }
    }
    Component.onCompleted: { hideTimer.start(); player.play(requestedEpisodeId, fromStart) }
}
