#include "qml/QmlPlayer.h"

#include "player/MpvCore.h"
#include "player/PlayerController.h"

#include <QFileInfo>
#include <QUrl>

namespace autoanime {

QmlPlayer::QmlPlayer(PlayerController *controller, MpvCore *core, QObject *parent)
    : QObject(parent)
    , m_controller(controller)
    , m_core(core)
{
    connect(controller, &PlayerController::playerReady, this, [this](qint64 episodeId) {
        m_episodeId = episodeId;
        m_loading = false;
        emit episodeIdChanged();
        emit loadingChanged();
    });
    connect(controller, &PlayerController::positionChanged, this, [this](double value) {
        m_position = value;
        emit positionChanged();
    });
    connect(controller, &PlayerController::durationChanged, this, [this](double value) {
        m_duration = value;
        emit durationChanged();
    });
    connect(controller, &PlayerController::pauseChanged, this, [this](bool value) {
        m_paused = value;
        emit pausedChanged();
    });
    connect(controller, &PlayerController::volumeChanged, this, [this](double value) {
        m_volume = value;
        emit volumeChanged();
    });
    connect(core, &MpvCore::muteChanged, this, [this](bool value) {
        m_muted = value;
        emit mutedChanged();
    });
    connect(core, &MpvCore::speedChanged, this, [this](double value) {
        m_speed = value;
        emit speedChanged();
    });
    connect(core, &MpvCore::diagnosticsChanged, this, [this](const QString &hwdec, qint64 dropped) {
        m_hwdec = hwdec;
        m_droppedFrames = dropped;
        emit diagnosticsChanged();
    });
    connect(controller, &PlayerController::trackListChanged, this, [this](const QList<MediaTrack> &tracks) {
        m_audioTracks.clear();
        m_subtitleTracks.clear();
        for (const MediaTrack &track : tracks) {
            QVariantMap item{
                {QStringLiteral("id"), track.id},
                {QStringLiteral("label"), track.displayName()},
                {QStringLiteral("selected"), track.selected},
            };
            if (track.type == QStringLiteral("audio")) {
                m_audioTracks.append(item);
            } else if (track.type == QStringLiteral("sub")) {
                m_subtitleTracks.append(item);
            }
        }
        emit tracksChanged();
    });
    connect(controller, &PlayerController::playbackError, this, [this](const QString &value) {
        m_error = value;
        m_loading = false;
        emit errorChanged();
        emit loadingChanged();
    });
    connect(controller, &PlayerController::playbackEnded, this, &QmlPlayer::playbackEnded);
    connect(controller, &PlayerController::playbackStopped, this, [this](qint64 episodeId) {
        m_episodeId = -1;
        m_position = 0.0;
        m_duration = 0.0;
        emit episodeIdChanged();
        emit positionChanged();
        emit durationChanged();
        emit playbackStopped(episodeId);
    });
}

void QmlPlayer::play(qint64 episodeId, bool fromStart)
{
    if (episodeId <= 0) {
        return;
    }
    m_error.clear();
    m_loading = true;
    emit errorChanged();
    emit loadingChanged();
    m_controller->playEpisode(episodeId, fromStart);
}

void QmlPlayer::togglePause()
{
    m_paused ? m_controller->resume() : m_controller->pause();
}

void QmlPlayer::seek(double seconds) { m_controller->seek(seconds); }
void QmlPlayer::seekRelative(double seconds) { m_core->seekRelative(seconds); }
void QmlPlayer::setVolume(double value) { m_controller->setVolume(value); }
void QmlPlayer::toggleMute() { m_core->setMuted(!m_muted); }
void QmlPlayer::setSpeed(double value) { m_core->setSpeed(value); }
void QmlPlayer::selectAudioTrack(qint64 id) { m_controller->selectAudioTrack(id); }
void QmlPlayer::selectSubtitleTrack(qint64 id) { m_controller->selectSubtitleTrack(id); }

void QmlPlayer::addSubtitle(const QUrl &url)
{
    const QString path = url.isLocalFile() ? url.toLocalFile() : url.toString();
    if (!path.isEmpty()) {
        m_core->addSubtitle(path);
    }
}

void QmlPlayer::stop() { m_controller->stop(); }

} // namespace autoanime
