#pragma once

#include <QObject>
#include <QVariantList>

namespace autoanime {

class MpvCore;
class PlayerController;

class QmlPlayer final : public QObject {
    Q_OBJECT
    Q_PROPERTY(qint64 episodeId READ episodeId NOTIFY episodeIdChanged)
    Q_PROPERTY(QString subjectTitle READ subjectTitle NOTIFY episodeMetadataChanged)
    Q_PROPERTY(QString episodeDisplayNumber READ episodeDisplayNumber NOTIFY episodeMetadataChanged)
    Q_PROPERTY(QString episodeTitle READ episodeTitle NOTIFY episodeMetadataChanged)
    Q_PROPERTY(double position READ position NOTIFY positionChanged)
    Q_PROPERTY(double duration READ duration NOTIFY durationChanged)
    Q_PROPERTY(double volume READ volume NOTIFY volumeChanged)
    Q_PROPERTY(double speed READ speed NOTIFY speedChanged)
    Q_PROPERTY(bool paused READ paused NOTIFY pausedChanged)
    Q_PROPERTY(bool muted READ muted NOTIFY mutedChanged)
    Q_PROPERTY(bool loading READ loading NOTIFY loadingChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QString hwdec READ hwdec NOTIFY diagnosticsChanged)
    Q_PROPERTY(qint64 droppedFrames READ droppedFrames NOTIFY diagnosticsChanged)
    Q_PROPERTY(QVariantList audioTracks READ audioTracks NOTIFY tracksChanged)
    Q_PROPERTY(QVariantList subtitleTracks READ subtitleTracks NOTIFY tracksChanged)

public:
    QmlPlayer(PlayerController *controller, MpvCore *core, QObject *parent = nullptr);

    qint64 episodeId() const noexcept { return m_episodeId; }
    QString subjectTitle() const { return m_subjectTitle; }
    QString episodeDisplayNumber() const { return m_episodeDisplayNumber; }
    QString episodeTitle() const { return m_episodeTitle; }
    double position() const noexcept { return m_position; }
    double duration() const noexcept { return m_duration; }
    double volume() const noexcept { return m_volume; }
    double speed() const noexcept { return m_speed; }
    bool paused() const noexcept { return m_paused; }
    bool muted() const noexcept { return m_muted; }
    bool loading() const noexcept { return m_loading; }
    QString error() const { return m_error; }
    QString hwdec() const { return m_hwdec; }
    qint64 droppedFrames() const noexcept { return m_droppedFrames; }
    QVariantList audioTracks() const { return m_audioTracks; }
    QVariantList subtitleTracks() const { return m_subtitleTracks; }

    Q_INVOKABLE void play(qint64 episodeId, bool fromStart = false);
    Q_INVOKABLE void togglePause();
    Q_INVOKABLE void seek(double seconds);
    Q_INVOKABLE void seekRelative(double seconds);
    Q_INVOKABLE void setVolume(double value);
    Q_INVOKABLE void toggleMute();
    Q_INVOKABLE void setSpeed(double value);
    Q_INVOKABLE void selectAudioTrack(qint64 id);
    Q_INVOKABLE void selectSubtitleTrack(qint64 id);
    Q_INVOKABLE void addSubtitle(const QUrl &url);
    Q_INVOKABLE void stop();

signals:
    void episodeIdChanged();
    void episodeMetadataChanged();
    void positionChanged();
    void durationChanged();
    void volumeChanged();
    void speedChanged();
    void pausedChanged();
    void mutedChanged();
    void loadingChanged();
    void errorChanged();
    void diagnosticsChanged();
    void tracksChanged();
    void playbackEnded(qint64 episodeId, qint64 nextEpisodeId);
    void playbackStopped(qint64 episodeId);

private:
    PlayerController *m_controller;
    MpvCore *m_core;
    qint64 m_episodeId{-1};
    QString m_subjectTitle;
    QString m_episodeDisplayNumber;
    QString m_episodeTitle;
    double m_position{0.0};
    double m_duration{0.0};
    double m_volume{100.0};
    double m_speed{1.0};
    bool m_paused{false};
    bool m_muted{false};
    bool m_loading{false};
    QString m_error;
    QString m_hwdec;
    qint64 m_droppedFrames{0};
    QVariantList m_audioTracks;
    QVariantList m_subtitleTracks;
};

} // namespace autoanime
