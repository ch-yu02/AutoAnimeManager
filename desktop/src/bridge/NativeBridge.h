#pragma once

#include "player/PlayerState.h"

#include <QObject>
#include <QVariantList>

namespace autoanime {

class PlayerController;

class NativeBridge final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool available READ available CONSTANT)

public:
    explicit NativeBridge(PlayerController *controller, QObject *parent = nullptr);

    [[nodiscard]] bool available() const noexcept { return true; }

public slots:
    void playEpisode(qint64 episodeId, bool fromStart = false);
    void pause();
    void resume();
    void seek(double seconds);
    void stop();
    void toggleFullscreen();
    void setVolume(double value);
    void selectAudioTrack(qint64 id);
    void selectSubtitleTrack(qint64 id);
    void setPlayerRect(
        double x,
        double y,
        double width,
        double height,
        double devicePixelRatio,
        bool visible
    );

signals:
    void playbackRequested(qint64 episodeId);
    void playerReady(qint64 episodeId);
    void playbackStarted(qint64 episodeId);
    void positionChanged(double seconds);
    void durationChanged(double seconds);
    void pauseChanged(bool paused);
    void volumeChanged(double value);
    void trackListChanged(const QVariantList &tracks);
    void playbackEnded(qint64 episodeId, qint64 nextEpisodeId);
    void playbackStopped(qint64 episodeId);
    void playbackError(const QString &message);
    void watchedChanged(qint64 episodeId, bool watched);
    void fullscreenRequested();
    void playerRectRequested(
        double x,
        double y,
        double width,
        double height,
        double devicePixelRatio,
        bool visible
    );

private:
    PlayerController *m_controller;
};

} // namespace autoanime
