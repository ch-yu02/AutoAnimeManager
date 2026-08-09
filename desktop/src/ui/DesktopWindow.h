#pragma once

#include <QMainWindow>
#include <QRectF>
#include <QUrl>

class QCloseEvent;
class QResizeEvent;
class QEvent;
class QMainWindow;
class QWidget;
class QWebEngineView;
class QWebChannel;

namespace autoanime {

class AppWebPage;
class BackendClient;
class MpvCore;
class MpvRenderWidget;
class NativeBridge;
class PlayerController;

class DesktopWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit DesktopWindow(
        QUrl frontendUrl,
        QUrl backendUrl,
        bool devtools,
        bool dedicatedPlayer,
        QWidget *parent = nullptr
    );
    ~DesktopWindow() override;

protected:
    void closeEvent(QCloseEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    bool eventFilter(QObject *watched, QEvent *event) override;

private slots:
    void bootstrapBridge(bool ok);
    void toggleFullscreen();
    void showPlayerSurface(qint64 episodeId);
    void hidePlayerSurface(qint64 episodeId);
    void updatePlayerSurface(
        double x,
        double y,
        double width,
        double height,
        double devicePixelRatio,
        bool visible
    );
    void reportPlayerError(const QString &message);

private:
    void buildUi();
    void setupBridge();
    void repositionPlayerSurface();
    void restoreGeometryState();
    void saveGeometryState();
    void openDevtools();
    void handlePageReset();
    void connectScreenChanges();

    QUrl m_frontendUrl;
    QUrl m_backendUrl;
    QWidget *m_centralWidget{nullptr};
    QWebEngineView *m_webView{nullptr};
    QWebEngineView *m_devtoolsView{nullptr};
    QMainWindow *m_dedicatedPlayerWindow{nullptr};
    QWebChannel *m_channel{nullptr};
    MpvCore *m_core{nullptr};
    MpvRenderWidget *m_renderWidget{nullptr};
    BackendClient *m_backendClient{nullptr};
    PlayerController *m_playerController{nullptr};
    NativeBridge *m_nativeBridge{nullptr};
    QRectF m_playerSlotRect;
    double m_playerSlotDevicePixelRatio{1.0};
    bool m_playerSlotVisible{false};
    bool m_playbackSurfaceRequested{false};
    bool m_dedicatedPlayer{false};
    bool m_screenChangesConnected{false};
};

} // namespace autoanime
