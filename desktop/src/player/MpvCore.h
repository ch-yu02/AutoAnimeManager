#pragma once

#include "player/PlayerState.h"

#include <QList>
#include <QObject>
#include <QStringList>

struct mpv_event;
struct mpv_handle;

namespace autoanime {

class MpvCore final : public QObject {
    Q_OBJECT

public:
    explicit MpvCore(QObject *parent = nullptr);
    ~MpvCore() override;

    MpvCore(const MpvCore &) = delete;
    MpvCore &operator=(const MpvCore &) = delete;

    [[nodiscard]] mpv_handle *nativeHandle() const noexcept { return m_handle; }
    [[nodiscard]] bool isPaused() const noexcept { return m_paused; }
    [[nodiscard]] bool isMuted() const noexcept { return m_muted; }
    [[nodiscard]] double position() const noexcept { return m_position; }
    [[nodiscard]] double duration() const noexcept { return m_duration; }
    [[nodiscard]] double volume() const noexcept { return m_volume; }

    void loadFile(const QString &path);
    void setPaused(bool paused);
    void togglePause();
    void seekAbsolute(double seconds);
    void seekRelative(double seconds);
    void setVolume(double value);
    void setMuted(bool muted);
    void selectAudioTrack(int id);
    void selectSubtitleTrack(int id);
    void addSubtitle(const QString &path);
    void stop();
    void shutdown();

signals:
    void fileLoaded(const QString &path);
    void positionChanged(double seconds);
    void durationChanged(double seconds);
    void pauseChanged(bool paused);
    void volumeChanged(double value);
    void muteChanged(bool muted);
    void trackListChanged(const QList<autoanime::MediaTrack> &tracks);
    void endFile(int reason, const QString &detail);
    void playbackError(const QString &message);
    void logMessage(const QString &message);
    void shutdownRequested();

private slots:
    void processEvents();

private:
    static void wakeup(void *context);
    void handleEvent(mpv_event *event);
    void observeProperties();
    void refreshTrackList();
    int command(const QStringList &arguments);
    int setFlag(const char *name, bool value);
    int setDouble(const char *name, double value);
    int setString(const char *name, const QString &value);
    void reportError(const QString &operation, int errorCode);

    mpv_handle *m_handle{nullptr};
    quint64 m_requestId{1};
    QString m_requestedPath;
    double m_position{0.0};
    double m_duration{0.0};
    double m_volume{100.0};
    bool m_paused{false};
    bool m_muted{false};
};

} // namespace autoanime
