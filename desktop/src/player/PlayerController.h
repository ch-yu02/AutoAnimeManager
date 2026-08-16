#pragma once

#include "player/PlayerState.h"

#include <QObject>
#include <QTimer>

namespace autoanime {

class BackendClient;
class MpvCore;

class PlayerController final : public QObject {
    Q_OBJECT

    friend class PlayerControllerActivityTest;

public:
    explicit PlayerController(MpvCore *core, BackendClient *backend, QObject *parent = nullptr);

public slots:
    void playEpisode(qint64 episodeId, bool fromStart = false);
    void pause();
    void resume();
    void seek(double seconds);
    void stop();
    void shutdown();
    void setVolume(double value);
    void selectAudioTrack(qint64 id);
    void selectSubtitleTrack(qint64 id);

signals:
    void playerReady(
        qint64 episodeId,
        const QString &subjectTitle,
        const QString &episodeDisplayNumber,
        const QString &episodeTitle
    );
    void playbackStarted(qint64 episodeId);
    void positionChanged(double seconds);
    void durationChanged(double seconds);
    void pauseChanged(bool paused);
    void volumeChanged(double value);
    void trackListChanged(const QList<autoanime::MediaTrack> &tracks);
    void playbackEnded(qint64 episodeId, qint64 nextEpisodeId);
    void playbackStopped(qint64 episodeId);
    void playbackError(const QString &message);
    void watchedChanged(qint64 episodeId, bool watched);
    void playbackActivityChanged(bool active);

private slots:
    void onSessionCreated(
        quint64 requestId,
        const QString &sessionId,
        qint64 episodeId,
        qint64 mediaFileId,
        const QString &mediaPath,
        const QString &subjectTitle,
        const QString &episodeDisplayNumber,
        const QString &episodeTitle,
        double initialPositionSeconds,
        double durationSeconds,
        bool hasDuration
    );
    void onFileLoaded(const QString &path);
    void onEndFile(int reason, const QString &detail);
    void onPositionChanged(double seconds);
    void onDurationChanged(double seconds);
    void onPauseChanged(bool paused);
    void onCorePlaybackError(const QString &message);
    void savePeriodicProgress();
    void onBackendError(quint64 requestId, const QString &operation, const QString &message);

private:
    void saveProgress(bool ended = false);
    void closeSession();
    void resetSession();
    void startEpisode(qint64 episodeId, bool fromStart);
    void requestTransition(int transition, bool ended = false);
    void finishTransition(qint64 nextEpisodeId = -1);
    void updatePlaybackActivity();

    MpvCore *m_core;
    BackendClient *m_backend;
    QTimer m_progressTimer;
    QString m_sessionId;
    QString m_mediaPath;
    QString m_subjectTitle;
    QString m_episodeDisplayNumber;
    QString m_episodeTitle;
    qint64 m_episodeId{-1};
    qint64 m_mediaFileId{-1};
    double m_position{0.0};
    double m_duration{0.0};
    double m_pendingPosition{0.0};
    bool m_hasBackendDuration{false};
    bool m_waitingForFile{false};
    bool m_fileLoaded{false};
    bool m_playbackActive{false};
    bool m_closing{false};
    quint64 m_requestGeneration{0};
    quint64 m_progressRequestGeneration{0};
    quint64 m_transitionRequestId{0};
    int m_pendingTransition{0};
    qint64 m_pendingEpisodeId{-1};
    bool m_pendingFromStart{false};
};

} // namespace autoanime
