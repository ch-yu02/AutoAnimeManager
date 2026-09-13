#include "player/PlayerController.h"

#include "backend/BackendClient.h"
#include "player/MpvCore.h"

#include <mpv/client.h>

#include <QEventLoop>
#include <QList>
#include <QMetaObject>
#include <QTimer>

namespace autoanime {

PlayerController::PlayerController(MpvCore *core, BackendClient *backend, QObject *parent)
    : QObject(parent)
    , m_core(core)
    , m_backend(backend)
{
    m_progressTimer.setInterval(15000);
    connect(&m_progressTimer, &QTimer::timeout, this, &PlayerController::savePeriodicProgress);
    connect(m_backend, &BackendClient::sessionCreated, this, &PlayerController::onSessionCreated);
    connect(m_backend, &BackendClient::progressSaved, this, [this](
        quint64 requestId,
        const QString &sessionId,
        bool watched,
        qint64 nextEpisodeId
    ) {
        if (sessionId == m_sessionId && watched && m_episodeId >= 0) {
            emit watchedChanged(m_episodeId, true);
        }
        const bool completesTransition = requestId != 0
            && requestId == m_transitionRequestId
            && sessionId == m_sessionId;
        finishProgressSave(requestId, sessionId, !completesTransition);
        if (completesTransition) {
            finishTransition(nextEpisodeId);
        }
    });
    connect(m_backend, &BackendClient::requestFailed, this, &PlayerController::onBackendError);
    connect(m_core, &MpvCore::fileLoaded, this, &PlayerController::onFileLoaded);
    connect(m_core, &MpvCore::endFile, this, &PlayerController::onEndFile);
    connect(m_core, &MpvCore::positionChanged, this, &PlayerController::onPositionChanged);
    connect(m_core, &MpvCore::durationChanged, this, &PlayerController::onDurationChanged);
    connect(m_core, &MpvCore::pauseChanged, this, &PlayerController::onPauseChanged);
    connect(m_core, &MpvCore::volumeChanged, this, &PlayerController::volumeChanged);
    connect(m_core, &MpvCore::trackListChanged, this, &PlayerController::trackListChanged);
    connect(m_core, &MpvCore::playbackError, this, &PlayerController::onCorePlaybackError);
}

void PlayerController::playEpisode(qint64 episodeId, bool fromStart)
{
    if (m_closing) {
        return;
    }
    m_pendingEpisodeId = episodeId;
    m_pendingFromStart = fromStart;
    if (!m_sessionId.isEmpty()) {
        requestTransition(1);
        return;
    }
    m_core->stop();
    resetSession();
    startEpisode(episodeId, fromStart);
}

void PlayerController::pause()
{
    m_core->setPaused(true);
    saveProgress();
}

void PlayerController::resume()
{
    m_core->setPaused(false);
}

void PlayerController::seek(double seconds)
{
    m_core->seekAbsolute(seconds);
    m_position = qMax(0.0, seconds);
    saveProgress();
}

void PlayerController::stop()
{
    if (m_episodeId >= 0) {
        m_fileLoaded = false;
        updatePlaybackActivity();
        requestTransition(2);
    }
}

void PlayerController::shutdown()
{
    m_closing = true;
    m_fileLoaded = false;
    updatePlaybackActivity();
    m_pendingTransition = 0;
    m_transitionRequestId = 0;
    if (!m_sessionId.isEmpty()) {
        QEventLoop loop;
        const QString sessionId = m_sessionId;
        const quint64 shutdownRequestId = ++m_progressRequestGeneration;
        const QMetaObject::Connection saved = connect(
            m_backend,
            &BackendClient::progressSaved,
            &loop,
            [&loop, sessionId, shutdownRequestId](
                quint64 requestId,
                const QString &savedSessionId,
                bool,
                qint64
            ) {
                if (requestId == shutdownRequestId && savedSessionId == sessionId) {
                    loop.quit();
                }
            }
        );
        const QMetaObject::Connection failed = connect(
            m_backend,
            &BackendClient::requestFailed,
            &loop,
            [&loop, shutdownRequestId](quint64 requestId, const QString &operation, const QString &) {
                if (requestId == shutdownRequestId && operation == QStringLiteral("保存播放进度")) {
                    loop.quit();
                }
            }
        );
        m_backend->savePlaybackProgress(
            sessionId,
            m_position,
            m_duration,
            false,
            shutdownRequestId
        );
        QTimer::singleShot(1500, &loop, &QEventLoop::quit);
        loop.exec();
        disconnect(saved);
        disconnect(failed);
        closeSession();
    }
    m_core->stop();
    resetSession();
}

void PlayerController::setVolume(double value)
{
    m_core->setVolume(value);
}

void PlayerController::selectAudioTrack(qint64 id)
{
    m_core->selectAudioTrack(static_cast<int>(id));
}

void PlayerController::selectSubtitleTrack(qint64 id)
{
    m_core->selectSubtitleTrack(static_cast<int>(id));
}

void PlayerController::onSessionCreated(
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
)
{
    if (requestId != m_requestGeneration || episodeId != m_episodeId) {
        m_backend->closePlaybackSession(sessionId);
        return;
    }
    m_sessionId = sessionId;
    m_mediaFileId = mediaFileId;
    m_mediaPath = mediaPath;
    m_subjectTitle = subjectTitle;
    m_episodeDisplayNumber = episodeDisplayNumber;
    m_episodeTitle = episodeTitle;
    m_pendingPosition = initialPositionSeconds;
    m_duration = hasDuration ? durationSeconds : 0.0;
    m_hasBackendDuration = hasDuration;
    m_waitingForFile = true;
    m_core->loadFile(mediaPath);
}

void PlayerController::onFileLoaded(const QString &path)
{
    if (!m_waitingForFile || path != m_mediaPath) {
        return;
    }
    m_waitingForFile = false;
    if (m_pendingPosition > 0.0) {
        m_core->seekAbsolute(m_pendingPosition);
    }
    // mpv keeps the pause property across loadfile calls. A previous paused
    // episode must not leave a newly opened or resumed episode paused while
    // the QML controls show active playback.
    m_core->setPaused(false);
    m_fileLoaded = true;
    updatePlaybackActivity();
    m_progressTimer.start();
    emit playerReady(m_episodeId, m_subjectTitle, m_episodeDisplayNumber, m_episodeTitle);
    emit playbackStarted(m_episodeId);
}

void PlayerController::onEndFile(int reason, const QString &detail)
{
    m_fileLoaded = false;
    updatePlaybackActivity();
    if (!detail.isEmpty()) {
        emit playbackError(detail);
    }
    const bool ended = reason == MPV_END_FILE_REASON_EOF;
    if (m_episodeId >= 0 && ended) {
        requestTransition(3, true);
    }
}

void PlayerController::onPositionChanged(double seconds)
{
    m_position = qMax(0.0, seconds);
    emit positionChanged(m_position);
}

void PlayerController::onDurationChanged(double seconds)
{
    if (!m_hasBackendDuration && seconds > 0.0) {
        m_duration = seconds;
    }
    emit durationChanged(seconds);
}

void PlayerController::onPauseChanged(bool paused)
{
    emit pauseChanged(paused);
    updatePlaybackActivity();
}

void PlayerController::onCorePlaybackError(const QString &message)
{
    m_fileLoaded = false;
    updatePlaybackActivity();
    emit playbackError(message);
}

void PlayerController::savePeriodicProgress()
{
    saveProgress();
}

void PlayerController::saveProgress(bool ended)
{
    queueProgressSave(ended);
}

void PlayerController::queueProgressSave(bool ended, quint64 requestId)
{
    if (m_sessionId.isEmpty()) {
        return;
    }
    if (m_progressSaveInFlight) {
        m_progressSavePending = true;
        m_pendingProgressPosition = m_position;
        m_pendingProgressDuration = m_duration;
        m_pendingProgressEnded = m_pendingProgressEnded || ended;
        if (requestId != 0) {
            m_pendingProgressRequestId = requestId;
        }
        return;
    }
    startProgressSave(m_position, m_duration, ended, requestId);
}

void PlayerController::startProgressSave(
    double position,
    double duration,
    bool ended,
    quint64 requestId
)
{
    if (requestId == 0) {
        requestId = ++m_progressRequestGeneration;
    }
    m_progressSaveInFlight = true;
    m_activeProgressRequestId = requestId;
    m_activeProgressSessionId = m_sessionId;
    m_backend->savePlaybackProgress(
        m_sessionId,
        position,
        duration,
        ended,
        requestId
    );
}

void PlayerController::finishProgressSave(
    quint64 requestId,
    const QString &sessionId,
    bool sendPending
)
{
    if (!m_progressSaveInFlight
        || requestId != m_activeProgressRequestId
        || sessionId != m_activeProgressSessionId) {
        return;
    }
    m_progressSaveInFlight = false;
    m_activeProgressRequestId = 0;
    m_activeProgressSessionId.clear();
    if (!sendPending || !m_progressSavePending || m_sessionId.isEmpty()) {
        m_progressSavePending = false;
        m_pendingProgressEnded = false;
        m_pendingProgressRequestId = 0;
        return;
    }
    const double position = m_pendingProgressPosition;
    const double duration = m_pendingProgressDuration;
    const bool ended = m_pendingProgressEnded;
    const quint64 pendingRequestId = m_pendingProgressRequestId;
    m_progressSavePending = false;
    m_pendingProgressEnded = false;
    m_pendingProgressRequestId = 0;
    startProgressSave(position, duration, ended, pendingRequestId);
}

void PlayerController::closeSession()
{
    if (!m_sessionId.isEmpty()) {
        m_backend->closePlaybackSession(m_sessionId);
    }
}

void PlayerController::resetSession()
{
    m_fileLoaded = false;
    updatePlaybackActivity();
    m_progressTimer.stop();
    m_sessionId.clear();
    m_mediaPath.clear();
    m_subjectTitle.clear();
    m_episodeDisplayNumber.clear();
    m_episodeTitle.clear();
    m_episodeId = -1;
    m_mediaFileId = -1;
    m_pendingPosition = 0.0;
    m_position = 0.0;
    m_duration = 0.0;
    m_hasBackendDuration = false;
    m_waitingForFile = false;
    m_progressSaveInFlight = false;
    m_progressSavePending = false;
    m_pendingProgressEnded = false;
    m_pendingProgressRequestId = 0;
    m_activeProgressRequestId = 0;
    m_activeProgressSessionId.clear();
}

void PlayerController::updatePlaybackActivity()
{
    const bool active = !m_closing && m_fileLoaded && !m_core->isPaused();
    if (active == m_playbackActive) {
        return;
    }
    m_playbackActive = active;
    emit playbackActivityChanged(active);
}

void PlayerController::startEpisode(qint64 episodeId, bool fromStart)
{
    m_episodeId = episodeId;
    m_backend->createPlaybackSession(episodeId, fromStart, ++m_requestGeneration);
}

void PlayerController::requestTransition(int transition, bool ended)
{
    if (m_transitionRequestId != 0) {
        if (transition != 3) {
            m_pendingTransition = transition;
        }
        return;
    }
    m_pendingTransition = transition;
    if (m_sessionId.isEmpty()) {
        finishTransition();
        return;
    }
    m_transitionRequestId = ++m_progressRequestGeneration;
    queueProgressSave(ended, m_transitionRequestId);
}

void PlayerController::finishTransition(qint64 nextEpisodeId)
{
    const int transition = m_pendingTransition;
    const qint64 previousEpisodeId = m_episodeId;
    const qint64 nextRequestedEpisodeId = m_pendingEpisodeId;
    const bool nextFromStart = m_pendingFromStart;
    m_pendingTransition = 0;
    m_transitionRequestId = 0;
    m_pendingEpisodeId = -1;
    m_pendingFromStart = false;
    closeSession();
    m_core->stop();
    resetSession();
    if (transition == 1 && nextRequestedEpisodeId >= 0) {
        startEpisode(nextRequestedEpisodeId, nextFromStart);
    } else if (transition == 2 && previousEpisodeId >= 0) {
        emit playbackStopped(previousEpisodeId);
    } else if (transition == 3 && previousEpisodeId >= 0) {
        emit playbackEnded(previousEpisodeId, nextEpisodeId);
    }
}

void PlayerController::onBackendError(quint64 requestId, const QString &operation, const QString &message)
{
    if (operation == QStringLiteral("保存播放进度")) {
        emit playbackWarning(QStringLiteral("播放进度暂未保存，将在播放过程中重试"));
        const bool failedTransition = requestId != 0 && requestId == m_transitionRequestId;
        finishProgressSave(requestId, m_activeProgressSessionId, !failedTransition);
        if (failedTransition) {
            finishTransition();
        }
        return;
    }
    if (operation == QStringLiteral("准备播放") && requestId == m_requestGeneration) {
        emit playbackError(QStringLiteral("%1：%2").arg(operation, message));
        const qint64 episodeId = m_episodeId;
        m_core->stop();
        resetSession();
        if (episodeId >= 0) {
            emit playbackStopped(episodeId);
        }
    }
}

} // namespace autoanime
