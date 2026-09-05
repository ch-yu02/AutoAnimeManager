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
    property point lastPointerPosition: Qt.point(-1, -1)
    property string displayedSubjectTitle: player.subjectTitle || subjectTitle
    property string displayedEpisodeTitle: {
        const number = player.episodeDisplayNumber
        const title = player.episodeTitle
        if (number && title) return "第 " + number + " 集 · " + title
        if (number) return "第 " + number + " 集"
        return title || ""
    }
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
    function handlePointerPosition(x, y) {
        if (Math.abs(x - lastPointerPosition.x) < 0.5
                && Math.abs(y - lastPointerPosition.y) < 0.5)
            return
        lastPointerPosition = Qt.point(x, y)
        revealControls()
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
    function exitFullscreen() {
        if (ApplicationWindow.window.visibility === Window.FullScreen)
            ApplicationWindow.window.showNormal()
    }
    function exitPlayback() {
        exitFullscreen()
        player.stop()
        root.back()
    }

    background: Rectangle { color: Theme.screenBlack }
    MpvVideoItem { anchors.fill: parent }

    HoverHandler {
        id: playerHover
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        cursorShape: root.controlsVisible || player.paused ? Qt.ArrowCursor : Qt.BlankCursor
        onPointChanged: root.handlePointerPosition(point.position.x, point.position.y)
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        cursorShape: root.controlsVisible || player.paused ? Qt.ArrowCursor : Qt.BlankCursor
        onClicked: { player.togglePause(); root.revealControls() }
        onDoubleClicked: root.toggleFullscreen()
    }

    Rectangle { anchors.fill: parent; visible: player.loading; color: Qt.rgba(0, 0, 0, 0.45); BusyIndicator { anchors.centerIn: parent; running: true } }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: Metrics.pageHeaderHeight
        opacity: root.controlsVisible || player.paused ? 1 : 0
        visible: opacity > 0
        gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0.82) } GradientStop { position: 1; color: "transparent" } }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Metrics.space4
            anchors.rightMargin: Metrics.space4
            IconButton { iconName: "arrow-left"; foreground: "white"; iconSize: 24; tooltip: "退出播放"; onClicked: root.exitPlayback() }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Label { Layout.fillWidth: true; text: root.displayedSubjectTitle; color: "white"; font.pixelSize: Typography.itemTitle; font.weight: Typography.semibold; elide: Text.ElideRight }
                Label { Layout.fillWidth: true; visible: text.length > 0; text: root.displayedEpisodeTitle; color: Qt.rgba(1, 1, 1, 0.72); font.pixelSize: Typography.meta; elide: Text.ElideRight }
            }
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
        opacity: root.controlsVisible || player.paused ? 1 : 0
        visible: opacity > 0
        gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.88) } }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: Metrics.space4
            anchors.rightMargin: Metrics.space4
            anchors.bottomMargin: Metrics.space3
            height: 76
            radius: Metrics.radiusM
            color: Qt.rgba(3 / 255, 4 / 255, 5 / 255, 0.82)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.14)
            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: Metrics.space2
                anchors.rightMargin: Metrics.space2
                anchors.topMargin: Metrics.space1
                anchors.bottomMargin: Metrics.space1
                spacing: 0
                PlayerSlider {
                    id: timeline
                    Layout.fillWidth: true
                    Layout.preferredHeight: 20
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
                    Layout.fillHeight: true
                    spacing: Metrics.space1
                    IconButton { iconName: "skip-back"; foreground: "white"; iconSize: 24; tooltip: "上一集"; enabled: root.currentIndex > 0; onClicked: root.playAdjacent(-1) }
                    IconButton { iconName: player.paused ? "play" : "pause"; foreground: "white"; iconSize: 24; tooltip: player.paused ? "播放（Space）" : "暂停（Space）"; onClicked: { player.togglePause(); root.revealControls() } }
                    IconButton { iconName: "skip-forward"; foreground: "white"; iconSize: 24; tooltip: "下一集"; enabled: root.currentIndex >= 0 && root.currentIndex + 1 < root.episodeModel.length; onClicked: root.playAdjacent(1) }
                    Rectangle { width: 8; height: 8; radius: 4; color: player.paused ? Theme.warning : Theme.accent }
                    Label { text: player.paused ? "已暂停" : "播放中"; color: "white"; font.pixelSize: Typography.meta; font.weight: Typography.medium }
                    Label { text: root.formatTime(root.seeking ? timeline.value : player.position) + " / " + root.formatTime(player.duration); color: Qt.rgba(1, 1, 1, 0.82); font.family: Typography.monoFamily; font.pixelSize: Typography.meta }
                    Item { Layout.fillWidth: true }
                    IconButton { iconName: player.muted ? "volume-x" : "volume-2"; foreground: "white"; tooltip: player.muted ? "取消静音（M）" : "静音（M）"; onClicked: player.toggleMute() }
                    PlayerSlider { Layout.preferredWidth: 112; from: 0; to: 100; value: player.volume; onMoved: player.setVolume(value) }
                    AppButton { text: player.speed.toFixed(2) + "×"; foreground: "white"; variant: "ghost"; onClicked: speedMenu.open(); Menu { id: speedMenu; Repeater { model: [0.5, 0.75, 1, 1.25, 1.5, 2]; delegate: MenuItem { required property var modelData; text: modelData + "×"; onTriggered: player.setSpeed(modelData) } } } }
                    IconButton { iconName: "audio-lines"; foreground: "white"; tooltip: "音轨"; onClicked: audioMenu.open(); Menu { id: audioMenu; Repeater { model: player.audioTracks; delegate: MenuItem { required property var modelData; text: (modelData.selected ? "✓ " : "") + modelData.label; onTriggered: player.selectAudioTrack(modelData.id) } } } }
                    IconButton { iconName: "captions"; foreground: "white"; tooltip: "字幕"; onClicked: subtitleMenu.open(); Menu { id: subtitleMenu; MenuItem { text: "关闭字幕"; onTriggered: player.selectSubtitleTrack(-1) } Repeater { model: player.subtitleTracks; delegate: MenuItem { required property var modelData; text: (modelData.selected ? "✓ " : "") + modelData.label; onTriggered: player.selectSubtitleTrack(modelData.id) } } MenuSeparator {} MenuItem { text: "打开字幕文件…"; onTriggered: subtitleDialog.open() } } }
                    IconButton { iconName: "maximize"; foreground: "white"; iconSize: 24; tooltip: "全屏（F）"; onClicked: root.toggleFullscreen() }
                }
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
    Shortcut { sequence: "Ctrl+Right"; onActivated: { player.seekRelative(85); root.revealControls() } }
    Shortcut { sequence: "Up"; onActivated: { player.setVolume(Math.min(100, player.volume + 5)); root.revealControls() } }
    Shortcut { sequence: "Down"; onActivated: { player.setVolume(Math.max(0, player.volume - 5)); root.revealControls() } }
    Shortcut { sequence: "M"; onActivated: player.toggleMute() }
    Shortcut { sequence: "F"; onActivated: root.toggleFullscreen() }
    Shortcut { sequence: "Escape"; enabled: ApplicationWindow.window.visibility === Window.FullScreen; onActivated: root.exitFullscreen() }
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
