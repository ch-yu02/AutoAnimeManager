#pragma once

#include "player/PlayerState.h"

#include <QMainWindow>
#include <QStringList>

class QCloseEvent;
class QComboBox;
class QLabel;
class QListWidget;
class QPushButton;
class QSlider;
class QVBoxLayout;

namespace autoanime {

class MpvCore;
class MpvRenderWidget;

class PlayerWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit PlayerWindow(
        QStringList initialFiles = {},
        bool smokeTest = false,
        QString initialSubtitle = {},
        QWidget *parent = nullptr
    );
    ~PlayerWindow() override;

signals:
    void smokeTestFinished(bool success, const QString &detail);

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void openMedia();
    void openSubtitle();
    void loadCurrent();
    void loadPrevious();
    void loadNext();
    void toggleFullscreen();
    void recreatePlayer();
    void updatePosition(double seconds);
    void updateDuration(double seconds);
    void updateTracks(const QList<autoanime::MediaTrack> &tracks);
    void handleFileLoaded(const QString &path);
    void handleEndFile(int reason, const QString &detail);
    void handlePlaybackError(const QString &message);

private:
    void buildUi();
    void initializePlayer();
    void destroyPlayer();
    void setPlaylist(const QStringList &files);
    void selectPlaylistIndex(int index);
    void updateTimelineLabel(double previewPosition = -1.0);
    void configureShortcuts();
    void runSmokeStep();

    QWidget *m_videoHost{nullptr};
    QVBoxLayout *m_videoLayout{nullptr};
    MpvCore *m_core{nullptr};
    MpvRenderWidget *m_renderWidget{nullptr};
    QSlider *m_timeline{nullptr};
    QSlider *m_volume{nullptr};
    QLabel *m_timeLabel{nullptr};
    QLabel *m_statusLabel{nullptr};
    QPushButton *m_pauseButton{nullptr};
    QPushButton *m_muteButton{nullptr};
    QComboBox *m_audioTracks{nullptr};
    QComboBox *m_subtitleTracks{nullptr};
    QListWidget *m_playlistWidget{nullptr};

    QStringList m_playlist;
    QString m_pendingExternalSubtitle;
    int m_playlistIndex{-1};
    double m_position{0.0};
    double m_duration{0.0};
    double m_pendingSeek{0.0};
    bool m_timelineDragging{false};
    bool m_smokeTest{false};
    bool m_smokeRecreated{false};
    bool m_smokeSawPosition{false};
    bool m_smokeSawDuration{false};
    bool m_smokeSawTracks{false};
    bool m_smokeSawSubtitle{false};
    bool m_smokeSawExternalSubtitle{false};
    bool m_smokeSawMultiAudio{false};
    bool m_smokeSawEof{false};
    bool m_smokeWaitingForEof{false};
    bool m_smokeRequiresExternalSubtitle{false};
    bool m_smokeFailed{false};
    bool m_closing{false};
    int m_smokeLoadedCount{0};
};

} // namespace autoanime
