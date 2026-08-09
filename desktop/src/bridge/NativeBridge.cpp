#include "bridge/NativeBridge.h"

#include "player/PlayerController.h"

namespace autoanime {

NativeBridge::NativeBridge(PlayerController *controller, QObject *parent)
    : QObject(parent)
    , m_controller(controller)
{
    connect(m_controller, &PlayerController::playerReady, this, &NativeBridge::playerReady);
    connect(m_controller, &PlayerController::playbackStarted, this, &NativeBridge::playbackStarted);
    connect(m_controller, &PlayerController::positionChanged, this, &NativeBridge::positionChanged);
    connect(m_controller, &PlayerController::durationChanged, this, &NativeBridge::durationChanged);
    connect(m_controller, &PlayerController::pauseChanged, this, &NativeBridge::pauseChanged);
    connect(m_controller, &PlayerController::volumeChanged, this, &NativeBridge::volumeChanged);
    connect(m_controller, &PlayerController::trackListChanged, this, [this](const QList<MediaTrack> &tracks) {
        QVariantList serialized;
        for (const MediaTrack &track : tracks) {
            serialized.append(QVariantMap{
                {QStringLiteral("id"), track.id},
                {QStringLiteral("type"), track.type},
                {QStringLiteral("title"), track.title},
                {QStringLiteral("language"), track.language},
                {QStringLiteral("codec"), track.codec},
                {QStringLiteral("selected"), track.selected},
                {QStringLiteral("external"), track.external},
            });
        }
        emit trackListChanged(serialized);
    });
    connect(m_controller, &PlayerController::playbackEnded, this, &NativeBridge::playbackEnded);
    connect(m_controller, &PlayerController::playbackStopped, this, &NativeBridge::playbackStopped);
    connect(m_controller, &PlayerController::playbackError, this, &NativeBridge::playbackError);
    connect(m_controller, &PlayerController::watchedChanged, this, &NativeBridge::watchedChanged);
}

void NativeBridge::playEpisode(qint64 episodeId, bool fromStart)
{
    emit playbackRequested(episodeId);
    m_controller->playEpisode(episodeId, fromStart);
}

void NativeBridge::pause()
{
    m_controller->pause();
}

void NativeBridge::resume()
{
    m_controller->resume();
}

void NativeBridge::seek(double seconds)
{
    m_controller->seek(seconds);
}

void NativeBridge::stop()
{
    m_controller->stop();
}

void NativeBridge::toggleFullscreen()
{
    emit fullscreenRequested();
}

void NativeBridge::setVolume(double value)
{
    m_controller->setVolume(value);
}

void NativeBridge::selectAudioTrack(qint64 id)
{
    m_controller->selectAudioTrack(id);
}

void NativeBridge::selectSubtitleTrack(qint64 id)
{
    m_controller->selectSubtitleTrack(id);
}

void NativeBridge::setPlayerRect(
    double x,
    double y,
    double width,
    double height,
    double devicePixelRatio,
    bool visible
)
{
    emit playerRectRequested(x, y, width, height, devicePixelRatio, visible);
}

} // namespace autoanime
