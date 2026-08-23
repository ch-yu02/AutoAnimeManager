#include "backend/BackendClient.h"
#include "backend/BackendSupervisor.h"
#include "player/MpvCore.h"
#include "player/MpvVideoItem.h"
#include "player/PlayerController.h"
#include "qml/QmlBackend.h"
#include "qml/DesktopPreferences.h"
#include "qml/QmlPlayer.h"
#include "qml/RoundedCornerMaskItem.h"
#include "system/SleepInhibitor.h"

#include <QCommandLineParser>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QSurfaceFormat>
#include <QNetworkProxy>

#include <clocale>

int main(int argc, char *argv[])
{
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);

    QSurfaceFormat format;
    format.setRenderableType(QSurfaceFormat::OpenGL);
    format.setVersion(3, 3);
    format.setProfile(QSurfaceFormat::CoreProfile);
    format.setSwapBehavior(QSurfaceFormat::DoubleBuffer);
    QSurfaceFormat::setDefaultFormat(format);

    QGuiApplication application(argc, argv);
    // The desktop client only talks to the local FastAPI service and loads
    // public poster URLs. Avoid libproxy worker crashes caused by malformed
    // desktop proxy environment state; backend integrations keep their own
    // independently configured network stack.
    QNetworkProxy::setApplicationProxy(QNetworkProxy::NoProxy);
    std::setlocale(LC_NUMERIC, "C");
    QCoreApplication::setApplicationName(QStringLiteral("AutoAnime"));
    QCoreApplication::setOrganizationName(QStringLiteral("AutoAnime"));
    QCoreApplication::setApplicationVersion(QStringLiteral("0.2.0"));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("AutoAnime Qt Quick 原生客户端"));
    parser.addHelpOption();
    parser.addVersionOption();
    QCommandLineOption backendOption(
        QStringList{QStringLiteral("backend-url")},
        QStringLiteral("FastAPI 地址"),
        QStringLiteral("url"),
        QStringLiteral("http://127.0.0.1:8765/")
    );
    QCommandLineOption playEpisodeOption(
        QStringList{QStringLiteral("play-episode")},
        QStringLiteral("启动后直接播放指定 Episode（用于性能基线和验收）"),
        QStringLiteral("id")
    );
    QCommandLineOption externalBackendOption(
        QStringList{QStringLiteral("external-backend")},
        QStringLiteral("只连接外部启动的 FastAPI，不由客户端管理后端进程")
    );
    QCommandLineOption supervisorSmokeTestOption(
        QStringList{QStringLiteral("supervisor-smoke-test")},
        QStringLiteral("验证 backend 启停后立即退出（发布验收）")
    );
    parser.addOption(backendOption);
    parser.addOption(playEpisodeOption);
    parser.addOption(externalBackendOption);
    parser.addOption(supervisorSmokeTestOption);
    parser.process(application);

    if (parser.isSet(supervisorSmokeTestOption)) {
        qputenv("AUTOANIME_SCHEDULER__ENABLED", "false");
    }

    const QUrl backendUrl(parser.value(backendOption));
    if (!backendUrl.isValid()) {
        qCritical("FastAPI 地址无效");
        return 2;
    }

    qmlRegisterType<autoanime::MpvVideoItem>("AutoAnime", 1, 0, "MpvVideoItem");
    qmlRegisterType<autoanime::RoundedCornerMaskItem>("AutoAnime", 1, 0, "RoundedCornerMaskItem");

    autoanime::BackendSupervisor supervisor(
        backendUrl,
        !parser.isSet(externalBackendOption)
    );
    QString backendError;
    if (!supervisor.ensureReady(&backendError)) {
        qCritical("AutoAnime backend 启动失败：%s", qUtf8Printable(backendError));
        QQmlApplicationEngine errorEngine;
        errorEngine.addImportPath(QStringLiteral("qrc:/"));
        errorEngine.rootContext()->setContextProperty(QStringLiteral("startupError"), backendError);
        errorEngine.load(QUrl(QStringLiteral("qrc:/AutoAnime/qml/StartupError.qml")));
        if (!errorEngine.rootObjects().isEmpty()) {
            application.exec();
        }
        return 3;
    }
    if (parser.isSet(supervisorSmokeTestOption)) {
        supervisor.stop();
        return 0;
    }

    try {
        autoanime::MpvCore core;
        autoanime::MpvVideoItem::setCore(&core);
        autoanime::BackendClient playbackBackend(backendUrl);
        autoanime::SleepInhibitor sleepInhibitor;
        autoanime::PlayerController controller(&core, &playbackBackend);
        autoanime::QmlPlayer player(&controller, &core);
        autoanime::QmlBackend backend(backendUrl);
        autoanime::DesktopPreferences preferences;
        QObject::connect(
            &controller,
            &autoanime::PlayerController::playbackActivityChanged,
            &sleepInhibitor,
            &autoanime::SleepInhibitor::setInhibited
        );
        QObject::connect(&core, &autoanime::MpvCore::diagnosticsChanged, [](const QString &hwdec, qint64 dropped) {
            qInfo("libmpv diagnostics: hwdec=%s dropped_frames=%lld", qUtf8Printable(hwdec), static_cast<long long>(dropped));
        });

        QQmlApplicationEngine engine;
        engine.addImportPath(QStringLiteral("qrc:/"));
        engine.rootContext()->setContextProperty(QStringLiteral("backend"), &backend);
        engine.rootContext()->setContextProperty(QStringLiteral("player"), &player);
        engine.rootContext()->setContextProperty(QStringLiteral("preferences"), &preferences);
        engine.rootContext()->setContextProperty(
            QStringLiteral("startupEpisodeId"),
            parser.value(playEpisodeOption).toLongLong()
        );
        QObject::connect(&application, &QCoreApplication::aboutToQuit, &controller, &autoanime::PlayerController::shutdown);
        QObject::connect(&application, &QCoreApplication::aboutToQuit, &supervisor, &autoanime::BackendSupervisor::stop);
        engine.load(QUrl(QStringLiteral("qrc:/AutoAnime/qml/Main.qml")));
        if (engine.rootObjects().isEmpty()) {
            return 1;
        }
        const int result = application.exec();
        autoanime::MpvVideoItem::setCore(nullptr);
        return result;
    } catch (const std::exception &error) {
        qCritical("无法启动 AutoAnime：%s", error.what());
        return 1;
    }
}
