#include "ui/DesktopWindow.h"

#include "backend/BackendClient.h"
#include "bridge/NativeBridge.h"
#include "player/MpvCore.h"
#include "player/MpvRenderWidget.h"
#include "player/PlayerController.h"
#include "ui/AppWebPage.h"
#include "ui/PlayerSurfaceGeometry.h"

#include <QCloseEvent>
#include <QEvent>
#include <QMainWindow>
#include <QResizeEvent>
#include <QSettings>
#include <QStatusBar>
#include <QVBoxLayout>
#include <QWebChannel>
#include <QWebEnginePage>
#include <QWebEngineSettings>
#include <QWebEngineView>
#include <QWindow>
#include <QWidget>
#include <QTimer>

#include <utility>

namespace autoanime {

DesktopWindow::DesktopWindow(
    QUrl frontendUrl,
    QUrl backendUrl,
    bool devtools,
    bool dedicatedPlayer,
    QWidget *parent
)
    : QMainWindow(parent)
    , m_frontendUrl(std::move(frontendUrl))
    , m_backendUrl(std::move(backendUrl))
    , m_dedicatedPlayer(dedicatedPlayer)
{
    setWindowTitle(QStringLiteral("AutoAnime Desktop"));
    resize(1440, 900);
    buildUi();
    setupBridge();
    restoreGeometryState();
    if (devtools) {
        openDevtools();
    }
    m_webView->load(m_frontendUrl);
    QTimer::singleShot(0, this, &DesktopWindow::connectScreenChanges);
}

DesktopWindow::~DesktopWindow()
{
    saveGeometryState();
}

void DesktopWindow::buildUi()
{
    m_centralWidget = new QWidget(this);
    auto *layout = new QVBoxLayout(m_centralWidget);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    m_core = new MpvCore(this);
    m_webView = new QWebEngineView(m_centralWidget);
    m_webView->setPage(new AppWebPage(m_frontendUrl, m_webView));
    m_webView->settings()->setAttribute(QWebEngineSettings::FullScreenSupportEnabled, true);
    m_webView->settings()->setAttribute(QWebEngineSettings::LocalContentCanAccessRemoteUrls, false);
    layout->addWidget(m_webView, 1);

    QWidget *renderParent = m_centralWidget;
    if (m_dedicatedPlayer) {
        m_dedicatedPlayerWindow = new QMainWindow(this, Qt::Window);
        m_dedicatedPlayerWindow->setWindowTitle(QStringLiteral("AutoAnime Native Player"));
        m_dedicatedPlayerWindow->resize(1280, 720);
        m_dedicatedPlayerWindow->installEventFilter(this);
        renderParent = m_dedicatedPlayerWindow;
    }
    m_renderWidget = new MpvRenderWidget(m_core, renderParent);
    m_renderWidget->setMinimumSize(0, 0);
    m_renderWidget->setAttribute(Qt::WA_TransparentForMouseEvents, !m_dedicatedPlayer);
    m_renderWidget->setVisible(false);
    if (m_dedicatedPlayer) {
        m_dedicatedPlayerWindow->setCentralWidget(m_renderWidget);
    } else {
        m_renderWidget->raise();
    }
    setCentralWidget(m_centralWidget);

    connect(m_webView, &QWebEngineView::loadFinished, this, &DesktopWindow::bootstrapBridge);
    connect(m_webView, &QWebEngineView::loadStarted, this, &DesktopWindow::handlePageReset);
    connect(m_webView, &QWebEngineView::renderProcessTerminated, this, [this](
        QWebEnginePage::RenderProcessTerminationStatus,
        int
    ) {
        handlePageReset();
    });
}

void DesktopWindow::setupBridge()
{
    m_backendClient = new BackendClient(m_backendUrl, this);
    m_playerController = new PlayerController(m_core, m_backendClient, this);
    m_nativeBridge = new NativeBridge(m_playerController, this);
    m_channel = new QWebChannel(m_webView->page());
    m_channel->registerObject(QStringLiteral("nativeBridge"), m_nativeBridge);
    m_webView->page()->setWebChannel(m_channel);

    connect(m_nativeBridge, &NativeBridge::fullscreenRequested, this, &DesktopWindow::toggleFullscreen);
    connect(m_nativeBridge, &NativeBridge::playbackRequested, this, &DesktopWindow::showPlayerSurface);
    connect(m_nativeBridge, &NativeBridge::playerRectRequested, this, &DesktopWindow::updatePlayerSurface);
    connect(m_playerController, &PlayerController::playbackStarted, this, &DesktopWindow::showPlayerSurface);
    connect(m_playerController, &PlayerController::playbackStopped, this, &DesktopWindow::hidePlayerSurface);
    connect(m_playerController, &PlayerController::playbackEnded, this, [this](qint64 episodeId, qint64) {
        hidePlayerSurface(episodeId);
    });
    connect(m_playerController, &PlayerController::playbackError, this, &DesktopWindow::reportPlayerError);
}

void DesktopWindow::bootstrapBridge(bool ok)
{
    if (!ok) {
        return;
    }
    const QString script = QStringLiteral(R"JS(
(function () {
  function bootstrap() {
    if (!window.qt || !qt.webChannelTransport || !window.QWebChannel) return;
    new QWebChannel(qt.webChannelTransport, function (channel) {
      window.autoanimeNative = channel.objects.nativeBridge;
      window.dispatchEvent(new Event('autoanime-native-ready'));
    });
  }
  if (window.QWebChannel) bootstrap();
  else {
    var script = document.createElement('script');
    script.src = 'qrc:///qtwebchannel/qwebchannel.js';
    script.onload = bootstrap;
    document.head.appendChild(script);
  }
})();
)JS");
    m_webView->page()->runJavaScript(script);
}

void DesktopWindow::toggleFullscreen()
{
    QWidget *target = m_dedicatedPlayer && m_dedicatedPlayerWindow != nullptr
        ? static_cast<QWidget *>(m_dedicatedPlayerWindow)
        : static_cast<QWidget *>(this);
    if (target->isFullScreen()) {
        target->showNormal();
    } else {
        target->showFullScreen();
    }
}

void DesktopWindow::showPlayerSurface(qint64)
{
    m_playbackSurfaceRequested = true;
    repositionPlayerSurface();
}

void DesktopWindow::hidePlayerSurface(qint64)
{
    m_playbackSurfaceRequested = false;
    m_renderWidget->setVisible(false);
    if (m_dedicatedPlayerWindow != nullptr) {
        m_dedicatedPlayerWindow->hide();
    }
}

void DesktopWindow::updatePlayerSurface(
    double x,
    double y,
    double width,
    double height,
    double devicePixelRatio,
    bool visible
)
{
    m_playerSlotRect = QRectF(x, y, width, height);
    m_playerSlotDevicePixelRatio = devicePixelRatio > 0.0 ? devicePixelRatio : 1.0;
    m_playerSlotVisible = visible;
    repositionPlayerSurface();
}

void DesktopWindow::repositionPlayerSurface()
{
    if (m_centralWidget == nullptr || m_webView == nullptr || m_renderWidget == nullptr) {
        return;
    }
    if (m_dedicatedPlayer) {
        if (!m_playbackSurfaceRequested) {
            m_renderWidget->setVisible(false);
            if (m_dedicatedPlayerWindow != nullptr) {
                m_dedicatedPlayerWindow->hide();
            }
            return;
        }
        m_renderWidget->setVisible(true);
        m_dedicatedPlayerWindow->show();
        m_dedicatedPlayerWindow->raise();
        return;
    }
    if (!m_playbackSurfaceRequested || !m_playerSlotVisible || m_playerSlotRect.width() <= 0.0 || m_playerSlotRect.height() <= 0.0) {
        m_renderWidget->setVisible(false);
        return;
    }

    const QPoint origin = m_webView->mapTo(m_centralWidget, QPoint(0, 0));
    const QRect target = playerSurfaceGeometry(
        origin,
        m_playerSlotRect,
        m_playerSlotDevicePixelRatio,
        m_renderWidget->devicePixelRatioF()
    );
    if (m_renderWidget->geometry() != target) {
        m_renderWidget->setGeometry(target);
    }
    if (!m_renderWidget->isVisible()) {
        m_renderWidget->raise();
        m_renderWidget->show();
    }
}

void DesktopWindow::reportPlayerError(const QString &message)
{
    statusBar()->showMessage(message, 10000);
}

void DesktopWindow::restoreGeometryState()
{
    QSettings settings(QStringLiteral("AutoAnime"), QStringLiteral("AutoAnime Desktop"));
    const QByteArray geometry = settings.value(QStringLiteral("window/geometry")).toByteArray();
    if (!geometry.isEmpty()) {
        restoreGeometry(geometry);
    }
}

void DesktopWindow::saveGeometryState()
{
    QSettings settings(QStringLiteral("AutoAnime"), QStringLiteral("AutoAnime Desktop"));
    settings.setValue(QStringLiteral("window/geometry"), saveGeometry());
}

void DesktopWindow::openDevtools()
{
    m_devtoolsView = new QWebEngineView();
    m_devtoolsView->setAttribute(Qt::WA_DeleteOnClose);
    m_devtoolsView->resize(1000, 700);
    m_webView->page()->setDevToolsPage(m_devtoolsView->page());
    m_devtoolsView->show();
}

void DesktopWindow::handlePageReset()
{
    m_playerSlotVisible = false;
    m_playerSlotRect = QRectF{};
    hidePlayerSurface(-1);
    if (m_playerController != nullptr) {
        m_playerController->stop();
    }
}

void DesktopWindow::connectScreenChanges()
{
    if (m_screenChangesConnected || windowHandle() == nullptr) {
        return;
    }
    m_screenChangesConnected = true;
    connect(windowHandle(), &QWindow::screenChanged, this, [this] {
        repositionPlayerSurface();
        if (m_webView != nullptr && m_webView->page() != nullptr) {
            m_webView->page()->runJavaScript(QStringLiteral(
                "window.dispatchEvent(new Event('autoanime-native-geometry'))"
            ));
        }
    });
}

void DesktopWindow::closeEvent(QCloseEvent *event)
{
    saveGeometryState();
    if (m_playerController != nullptr) {
        m_playerController->shutdown();
    }
    QMainWindow::closeEvent(event);
}

void DesktopWindow::resizeEvent(QResizeEvent *event)
{
    QMainWindow::resizeEvent(event);
    repositionPlayerSurface();
}

bool DesktopWindow::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == m_dedicatedPlayerWindow && event->type() == QEvent::Close) {
        if (m_playerController != nullptr) {
            m_playerController->stop();
        }
        m_playbackSurfaceRequested = false;
    }
    return QMainWindow::eventFilter(watched, event);
}

} // namespace autoanime
