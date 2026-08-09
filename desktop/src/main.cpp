#include "ui/PlayerWindow.h"

#include <QApplication>
#include <QCommandLineParser>
#include <QFileInfo>
#include <QOpenGLContext>
#include <QSurfaceFormat>
#include <QTimer>

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
    QCoreApplication::setApplicationName(QStringLiteral("AutoAnime Stage 3B Probe"));
    QCoreApplication::setApplicationVersion(QStringLiteral("0.1.0"));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Qt 6 + libmpv Render API 技术验证程序"));
    parser.addHelpOption();
    parser.addVersionOption();
    QCommandLineOption smokeOption(
        QStringList{QStringLiteral("smoke-test")},
        QStringLiteral("自动执行播放、seek、切集、全屏、resize 和重建验证后退出")
    );
    parser.addOption(smokeOption);
    QCommandLineOption subtitleOption(
        QStringList{QStringLiteral("subtitle")},
        QStringLiteral("首个媒体加载后自动添加的外挂字幕"),
        QStringLiteral("path")
    );
    parser.addOption(subtitleOption);
    parser.addPositionalArgument(QStringLiteral("media"), QStringLiteral("要播放的本地媒体文件，可传多个"));
    parser.process(application);

    QStringList files;
    for (const QString &path : parser.positionalArguments()) {
        const QFileInfo info(path);
        if (!info.isFile()) {
            qCritical("媒体文件不存在：%s", qUtf8Printable(path));
            return 2;
        }
        files.append(info.absoluteFilePath());
    }
    const bool smokeTest = parser.isSet(smokeOption);
    if (smokeTest && files.size() < 3) {
        qCritical("--smoke-test 至少需要 3 个媒体文件，用于连续切换验证");
        return 2;
    }

    QString subtitlePath;
    if (parser.isSet(subtitleOption)) {
        const QFileInfo subtitleInfo(parser.value(subtitleOption));
        if (!subtitleInfo.isFile()) {
            qCritical("外挂字幕不存在：%s", qUtf8Printable(parser.value(subtitleOption)));
            return 2;
        }
        subtitlePath = subtitleInfo.absoluteFilePath();
    }

    autoanime::PlayerWindow window(files, smokeTest, subtitlePath);
    if (smokeTest) {
        QObject::connect(
            &window,
            &autoanime::PlayerWindow::smokeTestFinished,
            &application,
            [&application](bool success, const QString &detail) {
                if (success) {
                    qInfo("Stage 3B smoke PASS: %s", qUtf8Printable(detail));
                } else {
                    qCritical("Stage 3B smoke FAIL: %s", qUtf8Printable(detail));
                }
                application.exit(success ? 0 : 1);
            }
        );
        QTimer::singleShot(30000, &application, [&application] {
            qCritical("Stage 3B smoke FAIL: 30 秒超时");
            application.exit(1);
        });
    }
    window.show();
    return application.exec();
}
