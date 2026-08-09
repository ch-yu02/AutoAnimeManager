#include "ui/PlayerWindow.h"

#include "player/MpvCore.h"
#include "player/MpvRenderWidget.h"

#include <mpv/client.h>

#include <QCloseEvent>
#include <QComboBox>
#include <QDebug>
#include <QFileDialog>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QShortcut>
#include <QSignalBlocker>
#include <QSlider>
#include <QSplitter>
#include <QStatusBar>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace autoanime {

PlayerWindow::PlayerWindow(
    QStringList initialFiles,
    bool smokeTest,
    QString initialSubtitle,
    QWidget *parent
)
    : QMainWindow(parent)
    , m_pendingExternalSubtitle(std::move(initialSubtitle))
    , m_smokeTest(smokeTest)
    , m_smokeRequiresExternalSubtitle(!m_pendingExternalSubtitle.isEmpty())
{
    setWindowTitle(QStringLiteral("AutoAnime Stage 3B · libmpv Probe"));
    resize(1280, 820);
    buildUi();
    configureShortcuts();
    setPlaylist(initialFiles);
    initializePlayer();
}

PlayerWindow::~PlayerWindow()
{
    destroyPlayer();
}

void PlayerWindow::closeEvent(QCloseEvent *event)
{
    m_closing = true;
    destroyPlayer();
    QMainWindow::closeEvent(event);
}

void PlayerWindow::openMedia()
{
    const QStringList files = QFileDialog::getOpenFileNames(
        this,
        QStringLiteral("选择本地动画"),
        QString{},
        QStringLiteral("视频 (*.mkv *.mp4 *.m4v *.webm *.avi);;所有文件 (*)")
    );
    if (!files.isEmpty()) {
        setPlaylist(files);
        loadCurrent();
    }
}

void PlayerWindow::openSubtitle()
{
    const QString path = QFileDialog::getOpenFileName(
        this,
        QStringLiteral("加载外挂字幕"),
        QString{},
        QStringLiteral("字幕 (*.ass *.ssa *.srt *.vtt);;所有文件 (*)")
    );
    if (!path.isEmpty() && m_core != nullptr) {
        m_core->addSubtitle(path);
    }
}

void PlayerWindow::loadCurrent()
{
    if (m_core == nullptr || m_playlistIndex < 0 || m_playlistIndex >= m_playlist.size()) {
        return;
    }
    m_statusLabel->setText(QStringLiteral("正在加载：%1").arg(m_playlist.at(m_playlistIndex)));
    m_core->loadFile(m_playlist.at(m_playlistIndex));
}

void PlayerWindow::loadPrevious()
{
    if (m_playlistIndex > 0) {
        selectPlaylistIndex(m_playlistIndex - 1);
        loadCurrent();
    }
}

void PlayerWindow::loadNext()
{
    if (m_playlistIndex + 1 < m_playlist.size()) {
        selectPlaylistIndex(m_playlistIndex + 1);
        loadCurrent();
    }
}

void PlayerWindow::toggleFullscreen()
{
    if (isFullScreen()) {
        showNormal();
    } else {
        showFullScreen();
    }
}

void PlayerWindow::recreatePlayer()
{
    if (m_closing) {
        return;
    }
    m_pendingSeek = m_position;
    destroyPlayer();
    initializePlayer();
    m_statusLabel->setText(QStringLiteral("播放器已销毁并重新创建"));
}

void PlayerWindow::updatePosition(double seconds)
{
    m_position = std::max(0.0, seconds);
    m_smokeSawPosition = true;
    if (!m_timelineDragging && m_duration > 0.0) {
        const QSignalBlocker blocker(m_timeline);
        m_timeline->setValue(qRound((m_position / m_duration) * 1000.0));
    }
    updateTimelineLabel();
}

void PlayerWindow::updateDuration(double seconds)
{
    m_duration = std::max(0.0, seconds);
    if (m_duration > 0.0) {
        m_smokeSawDuration = true;
    }
    updateTimelineLabel();
}

void PlayerWindow::updateTracks(const QList<MediaTrack> &tracks)
{
    const QSignalBlocker audioBlocker(m_audioTracks);
    const QSignalBlocker subtitleBlocker(m_subtitleTracks);
    m_audioTracks->clear();
    m_subtitleTracks->clear();
    m_audioTracks->addItem(QStringLiteral("无音轨"), -1);
    m_subtitleTracks->addItem(QStringLiteral("关闭字幕"), -1);

    bool hasVideo = false;
    bool hasAudio = false;
    int audioCount = 0;
    for (const MediaTrack &track : tracks) {
        if (track.type == QStringLiteral("video")) {
            hasVideo = true;
        } else if (track.type == QStringLiteral("audio")) {
            hasAudio = true;
            ++audioCount;
            m_audioTracks->addItem(track.displayName(), track.id);
            if (track.selected) {
                m_audioTracks->setCurrentIndex(m_audioTracks->count() - 1);
            }
        } else if (track.type == QStringLiteral("sub")) {
            m_smokeSawSubtitle = true;
            m_smokeSawExternalSubtitle = m_smokeSawExternalSubtitle || track.external;
            m_subtitleTracks->addItem(track.displayName(), track.id);
            if (track.selected) {
                m_subtitleTracks->setCurrentIndex(m_subtitleTracks->count() - 1);
            }
        }
    }
    m_smokeSawTracks = m_smokeSawTracks || (hasVideo && hasAudio);
    m_smokeSawMultiAudio = m_smokeSawMultiAudio || audioCount > 1;
}

void PlayerWindow::handleFileLoaded(const QString &path)
{
    if (m_smokeTest) {
        qInfo().noquote() << "smoke file-loaded" << path << "duration" << m_duration;
    }
    m_statusLabel->setText(QStringLiteral("已加载：%1").arg(path));
    if (m_pendingSeek > 0.0 && m_core != nullptr) {
        m_core->seekAbsolute(m_pendingSeek);
        m_pendingSeek = 0.0;
    }
    if (!m_pendingExternalSubtitle.isEmpty() && m_core != nullptr) {
        const QString subtitle = m_pendingExternalSubtitle;
        m_pendingExternalSubtitle.clear();
        m_core->addSubtitle(subtitle);
    }
    if (m_smokeTest) {
        ++m_smokeLoadedCount;
        QTimer::singleShot(500, this, &PlayerWindow::runSmokeStep);
    }
}

void PlayerWindow::handleEndFile(int reason, const QString &detail)
{
    if (m_smokeTest) {
        qInfo().noquote() << "smoke end-file reason" << reason << detail;
    }
    if (reason == MPV_END_FILE_REASON_EOF) {
        m_statusLabel->setText(QStringLiteral("播放结束"));
        if (m_smokeTest) {
            m_smokeSawEof = true;
            if (m_smokeWaitingForEof) {
                QTimer::singleShot(100, this, &PlayerWindow::runSmokeStep);
            }
        } else {
            loadNext();
        }
        return;
    }
    if (reason == MPV_END_FILE_REASON_STOP || reason == MPV_END_FILE_REASON_REDIRECT) {
        return;
    }
    handlePlaybackError(detail.isEmpty()
        ? QStringLiteral("播放异常结束，reason=%1").arg(reason)
        : QStringLiteral("播放异常结束：%1").arg(detail));
}

void PlayerWindow::handlePlaybackError(const QString &message)
{
    m_smokeFailed = true;
    m_statusLabel->setText(message);
    statusBar()->showMessage(message, 10000);
}

void PlayerWindow::buildUi()
{
    auto *central = new QWidget(this);
    auto *root = new QVBoxLayout(central);
    root->setContentsMargins(8, 8, 8, 8);

    auto *splitter = new QSplitter(Qt::Horizontal, central);
    m_videoHost = new QWidget(splitter);
    m_videoLayout = new QVBoxLayout(m_videoHost);
    m_videoLayout->setContentsMargins(0, 0, 0, 0);
    m_playlistWidget = new QListWidget(splitter);
    m_playlistWidget->setMinimumWidth(220);
    splitter->addWidget(m_videoHost);
    splitter->addWidget(m_playlistWidget);
    splitter->setStretchFactor(0, 1);
    splitter->setStretchFactor(1, 0);
    root->addWidget(splitter, 1);

    auto *timelineRow = new QHBoxLayout();
    m_timeline = new QSlider(Qt::Horizontal, central);
    m_timeline->setRange(0, 1000);
    m_timeLabel = new QLabel(QStringLiteral("0:00 / 0:00"), central);
    timelineRow->addWidget(m_timeline, 1);
    timelineRow->addWidget(m_timeLabel);
    root->addLayout(timelineRow);

    auto *controls = new QHBoxLayout();
    auto *openButton = new QPushButton(QStringLiteral("打开视频"), central);
    auto *previousButton = new QPushButton(QStringLiteral("上一项"), central);
    auto *nextButton = new QPushButton(QStringLiteral("下一项"), central);
    m_pauseButton = new QPushButton(QStringLiteral("暂停"), central);
    m_muteButton = new QPushButton(QStringLiteral("静音"), central);
    auto *subtitleButton = new QPushButton(QStringLiteral("加载外挂字幕"), central);
    auto *fullscreenButton = new QPushButton(QStringLiteral("全屏"), central);
    auto *recreateButton = new QPushButton(QStringLiteral("重建播放器"), central);
    m_volume = new QSlider(Qt::Horizontal, central);
    m_volume->setRange(0, 100);
    m_volume->setValue(100);
    m_volume->setMaximumWidth(140);
    m_audioTracks = new QComboBox(central);
    m_audioTracks->setMinimumWidth(150);
    m_subtitleTracks = new QComboBox(central);
    m_subtitleTracks->setMinimumWidth(150);

    controls->addWidget(openButton);
    controls->addWidget(previousButton);
    controls->addWidget(m_pauseButton);
    controls->addWidget(nextButton);
    controls->addWidget(new QLabel(QStringLiteral("音量"), central));
    controls->addWidget(m_volume);
    controls->addWidget(m_muteButton);
    controls->addWidget(new QLabel(QStringLiteral("音轨"), central));
    controls->addWidget(m_audioTracks);
    controls->addWidget(new QLabel(QStringLiteral("字幕"), central));
    controls->addWidget(m_subtitleTracks);
    controls->addWidget(subtitleButton);
    controls->addWidget(fullscreenButton);
    controls->addWidget(recreateButton);
    root->addLayout(controls);

    m_statusLabel = new QLabel(QStringLiteral("等待打开媒体"), central);
    m_statusLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    root->addWidget(m_statusLabel);
    setCentralWidget(central);

    connect(openButton, &QPushButton::clicked, this, &PlayerWindow::openMedia);
    connect(previousButton, &QPushButton::clicked, this, &PlayerWindow::loadPrevious);
    connect(nextButton, &QPushButton::clicked, this, &PlayerWindow::loadNext);
    connect(subtitleButton, &QPushButton::clicked, this, &PlayerWindow::openSubtitle);
    connect(fullscreenButton, &QPushButton::clicked, this, &PlayerWindow::toggleFullscreen);
    connect(recreateButton, &QPushButton::clicked, this, &PlayerWindow::recreatePlayer);
    connect(m_pauseButton, &QPushButton::clicked, this, [this] {
        if (m_core != nullptr) {
            m_core->togglePause();
        }
    });
    connect(m_muteButton, &QPushButton::clicked, this, [this] {
        if (m_core != nullptr) {
            m_core->setMuted(!m_core->isMuted());
        }
    });
    connect(m_volume, &QSlider::valueChanged, this, [this](int value) {
        if (m_core != nullptr) {
            m_core->setVolume(value);
        }
    });
    connect(m_audioTracks, &QComboBox::currentIndexChanged, this, [this](int index) {
        if (m_core != nullptr && index >= 0) {
            m_core->selectAudioTrack(m_audioTracks->itemData(index).toInt());
        }
    });
    connect(m_subtitleTracks, &QComboBox::currentIndexChanged, this, [this](int index) {
        if (m_core != nullptr && index >= 0) {
            m_core->selectSubtitleTrack(m_subtitleTracks->itemData(index).toInt());
        }
    });
    connect(m_playlistWidget, &QListWidget::currentRowChanged, this, [this](int row) {
        m_playlistIndex = row;
    });
    connect(m_playlistWidget, &QListWidget::itemDoubleClicked, this, [this] {
        loadCurrent();
    });
    connect(m_timeline, &QSlider::sliderPressed, this, [this] {
        m_timelineDragging = true;
    });
    connect(m_timeline, &QSlider::sliderMoved, this, [this](int value) {
        if (m_duration > 0.0) {
            updateTimelineLabel((value / 1000.0) * m_duration);
        }
    });
    connect(m_timeline, &QSlider::sliderReleased, this, [this] {
        m_timelineDragging = false;
        if (m_core != nullptr && m_duration > 0.0) {
            m_core->seekAbsolute((m_timeline->value() / 1000.0) * m_duration);
        }
    });
}

void PlayerWindow::initializePlayer()
{
    try {
        m_core = new MpvCore(this);
        m_renderWidget = new MpvRenderWidget(m_core, m_videoHost);
        m_videoLayout->insertWidget(0, m_renderWidget, 1);

        connect(m_renderWidget, &MpvRenderWidget::renderReady, this, &PlayerWindow::loadCurrent);
        connect(m_renderWidget, &MpvRenderWidget::renderError, this, &PlayerWindow::handlePlaybackError);
        connect(m_core, &MpvCore::fileLoaded, this, &PlayerWindow::handleFileLoaded);
        connect(m_core, &MpvCore::positionChanged, this, &PlayerWindow::updatePosition);
        connect(m_core, &MpvCore::durationChanged, this, &PlayerWindow::updateDuration);
        connect(m_core, &MpvCore::pauseChanged, this, [this](bool paused) {
            m_pauseButton->setText(paused ? QStringLiteral("播放") : QStringLiteral("暂停"));
        });
        connect(m_core, &MpvCore::volumeChanged, this, [this](double value) {
            const QSignalBlocker blocker(m_volume);
            m_volume->setValue(qRound(value));
        });
        connect(m_core, &MpvCore::muteChanged, this, [this](bool muted) {
            m_muteButton->setText(muted ? QStringLiteral("取消静音") : QStringLiteral("静音"));
        });
        connect(m_core, &MpvCore::trackListChanged, this, &PlayerWindow::updateTracks);
        connect(m_core, &MpvCore::endFile, this, &PlayerWindow::handleEndFile);
        connect(m_core, &MpvCore::playbackError, this, &PlayerWindow::handlePlaybackError);
        connect(m_core, &MpvCore::logMessage, this, [this](const QString &message) {
            statusBar()->showMessage(message, 5000);
        });
    } catch (const std::exception &error) {
        handlePlaybackError(QString::fromUtf8(error.what()));
        if (m_smokeTest) {
            QTimer::singleShot(0, this, [this, errorText = QString::fromUtf8(error.what())] {
                emit smokeTestFinished(false, errorText);
            });
        }
    }
}

void PlayerWindow::destroyPlayer()
{
    if (m_renderWidget != nullptr) {
        m_renderWidget->releaseRenderContext();
        m_videoLayout->removeWidget(m_renderWidget);
        delete m_renderWidget;
        m_renderWidget = nullptr;
    }
    if (m_core != nullptr) {
        m_core->shutdown();
        delete m_core;
        m_core = nullptr;
    }
}

void PlayerWindow::setPlaylist(const QStringList &files)
{
    m_playlist = files;
    m_playlistWidget->clear();
    for (const QString &path : files) {
        m_playlistWidget->addItem(path);
    }
    selectPlaylistIndex(files.isEmpty() ? -1 : 0);
}

void PlayerWindow::selectPlaylistIndex(int index)
{
    m_playlistIndex = index;
    const QSignalBlocker blocker(m_playlistWidget);
    m_playlistWidget->setCurrentRow(index);
}

void PlayerWindow::updateTimelineLabel(double previewPosition)
{
    const double shownPosition = previewPosition >= 0.0 ? previewPosition : m_position;
    m_timeLabel->setText(QStringLiteral("%1 / %2")
        .arg(formatTime(shownPosition), formatTime(m_duration)));
}

void PlayerWindow::configureShortcuts()
{
    connect(new QShortcut(QKeySequence(Qt::Key_Space), this), &QShortcut::activated, this, [this] {
        if (m_core != nullptr) {
            m_core->togglePause();
        }
    });
    connect(new QShortcut(QKeySequence(Qt::Key_Left), this), &QShortcut::activated, this, [this] {
        if (m_core != nullptr) {
            m_core->seekRelative(-5.0);
        }
    });
    connect(new QShortcut(QKeySequence(Qt::Key_Right), this), &QShortcut::activated, this, [this] {
        if (m_core != nullptr) {
            m_core->seekRelative(5.0);
        }
    });
    connect(new QShortcut(QKeySequence(Qt::Key_Up), this), &QShortcut::activated, this, [this] {
        m_volume->setValue(std::min(100, m_volume->value() + 5));
    });
    connect(new QShortcut(QKeySequence(Qt::Key_Down), this), &QShortcut::activated, this, [this] {
        m_volume->setValue(std::max(0, m_volume->value() - 5));
    });
    connect(new QShortcut(QKeySequence(Qt::Key_F), this), &QShortcut::activated,
            this, &PlayerWindow::toggleFullscreen);
    connect(new QShortcut(QKeySequence(Qt::Key_Escape), this), &QShortcut::activated, this, [this] {
        if (isFullScreen()) {
            showNormal();
        }
    });
    connect(new QShortcut(QKeySequence(Qt::Key_M), this), &QShortcut::activated, this, [this] {
        if (m_core != nullptr) {
            m_core->setMuted(!m_core->isMuted());
        }
    });
}

void PlayerWindow::runSmokeStep()
{
    if (!m_smokeTest || m_core == nullptr || m_closing) {
        return;
    }

    if (m_smokeRecreated) {
        if (!m_smokeWaitingForEof) {
            m_smokeWaitingForEof = true;
            const double eofStart = m_duration <= 15.0 ? 0.0 : std::max(0.0, m_duration - 2.0);
            qInfo() << "smoke waiting EOF from" << eofStart << "duration" << m_duration;
            m_core->seekAbsolute(eofStart);
            m_core->setPaused(false);
            return;
        }
        if (!m_smokeSawEof) {
            return;
        }
        const bool enoughLoads = m_smokeLoadedCount >= m_playlist.size() + 1;
        const bool externalSubtitleOk = !m_smokeRequiresExternalSubtitle || m_smokeSawExternalSubtitle;
        const bool success = !m_smokeFailed && enoughLoads
            && m_smokeSawPosition && m_smokeSawDuration && m_smokeSawTracks
            && m_smokeSawSubtitle && m_smokeSawMultiAudio && externalSubtitleOk && m_smokeSawEof;
        const QString detail = success
            ? QStringLiteral("load/seek/pause/track switch/ASS/resize/fullscreen/EOF/switch/recreate 全部通过")
            : QStringLiteral("smoke 未满足：loads=%1 position=%2 duration=%3 tracks=%4 subtitle=%5 external=%6 multiAudio=%7 eof=%8 error=%9")
                .arg(m_smokeLoadedCount)
                .arg(m_smokeSawPosition)
                .arg(m_smokeSawDuration)
                .arg(m_smokeSawTracks)
                .arg(m_smokeSawSubtitle)
                .arg(m_smokeSawExternalSubtitle)
                .arg(m_smokeSawMultiAudio)
                .arg(m_smokeSawEof)
                .arg(m_smokeFailed);
        emit smokeTestFinished(success, detail);
        return;
    }

    m_core->setPaused(true);
    m_core->seekAbsolute(std::min(5.0, std::max(0.0, m_duration / 2.0)));
    m_core->setVolume(35.0);
    if (m_audioTracks->count() > 2) {
        m_core->selectAudioTrack(m_audioTracks->itemData(2).toInt());
    }
    if (m_subtitleTracks->count() > 1) {
        m_core->selectSubtitleTrack(m_subtitleTracks->itemData(1).toInt());
    }
    resize(width() == 1280 ? 1024 : 1280, height() == 820 ? 680 : 820);
    if (m_smokeLoadedCount == 1) {
        toggleFullscreen();
        QTimer::singleShot(200, this, &PlayerWindow::toggleFullscreen);
    }
    QTimer::singleShot(250, this, [this] {
        if (m_core != nullptr) {
            m_core->setPaused(false);
        }
    });
    QTimer::singleShot(900, this, [this] {
        if (m_playlistIndex + 1 < m_playlist.size()) {
            loadNext();
            return;
        }
        if (!m_smokeRecreated) {
            m_smokeRecreated = true;
            recreatePlayer();
            return;
        }
    });
}

} // namespace autoanime
