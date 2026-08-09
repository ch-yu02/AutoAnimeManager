#include "ui/DesktopWindow.h"

#include <QApplication>
#include <QCommandLineParser>
#include <QSurfaceFormat>

#include <clocale>

int main(int argc, char *argv[])
{
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
    QSurfaceFormat format;
    format.setRenderableType(QSurfaceFormat::OpenGL);
    format.setVersion(3, 3);
    format.setProfile(QSurfaceFormat::CoreProfile);
    format.setSwapBehavior(QSurfaceFormat::DoubleBuffer);
    QSurfaceFormat::setDefaultFormat(format);

    QApplication application(argc, argv);
    std::setlocale(LC_NUMERIC, "C");
    QCoreApplication::setApplicationName(QStringLiteral("AutoAnime Desktop"));
    QCoreApplication::setApplicationVersion(QStringLiteral("0.1.0"));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("AutoAnime Qt WebEngine Desktop Shell"));
    parser.addHelpOption();
    parser.addVersionOption();
    QCommandLineOption devOption(
        QStringList{QStringLiteral("dev")},
        QStringLiteral("加载 Vite 开发服务器，而不是 FastAPI 提供的生产前端")
    );
    QCommandLineOption urlOption(
        QStringList{QStringLiteral("url")},
        QStringLiteral("覆盖前端 URL"),
        QStringLiteral("url")
    );
    QCommandLineOption backendOption(
        QStringList{QStringLiteral("backend-url")},
        QStringLiteral("FastAPI 地址"),
        QStringLiteral("url"),
        QStringLiteral("http://127.0.0.1:8765")
    );
    QCommandLineOption devtoolsOption(
        QStringList{QStringLiteral("devtools")},
        QStringLiteral("打开 Chromium DevTools")
    );
    QCommandLineOption dedicatedPlayerOption(
        QStringList{QStringLiteral("dedicated-player")},
        QStringLiteral("使用独立原生播放窗口，作为 WebEngine/OpenGL 层叠异常时的稳定 fallback")
    );
    parser.addOption(devOption);
    parser.addOption(urlOption);
    parser.addOption(backendOption);
    parser.addOption(devtoolsOption);
    parser.addOption(dedicatedPlayerOption);
    parser.process(application);

    const QUrl backendUrl(parser.value(backendOption));
    const QUrl frontendUrl = parser.isSet(urlOption)
        ? QUrl(parser.value(urlOption))
        : QUrl(parser.isSet(devOption)
            ? QStringLiteral("http://127.0.0.1:5173/")
            : QStringLiteral("http://127.0.0.1:8765/"));
    if (!frontendUrl.isValid() || !backendUrl.isValid()) {
        qCritical("前端或后端 URL 无效");
        return 2;
    }

    try {
        autoanime::DesktopWindow window(
            frontendUrl,
            backendUrl,
            parser.isSet(devtoolsOption),
            parser.isSet(dedicatedPlayerOption)
        );
        window.show();
        return application.exec();
    } catch (const std::exception &error) {
        qCritical("无法启动 AutoAnime Desktop：%s", error.what());
        return 1;
    }
}
