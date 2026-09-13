#include "player/PlayerState.h"

#include <QTest>

using autoanime::MediaTrack;
using autoanime::fitVideoWindowSize;
using autoanime::formatTime;

class PlayerStateTest final : public QObject {
    Q_OBJECT

private slots:
    void formatsPlaybackTime()
    {
        QCOMPARE(formatTime(0), QStringLiteral("0:00"));
        QCOMPARE(formatTime(65.2), QStringLiteral("1:05"));
        QCOMPARE(formatTime(3661), QStringLiteral("1:01:01"));
        QCOMPARE(formatTime(-1), QStringLiteral("0:00"));
    }

    void buildsReadableTrackLabels()
    {
        MediaTrack track;
        track.id = 3;
        track.type = QStringLiteral("sub");
        track.title = QStringLiteral("简体中文");
        track.language = QStringLiteral("chi");
        track.codec = QStringLiteral("ass");
        track.external = true;
        QCOMPARE(track.displayName(), QStringLiteral("简体中文 · chi / ass / 外挂"));
    }

    void fitsWindowToVideoAndAvailableScreen()
    {
        QCOMPARE(fitVideoWindowSize(1280, 720, 2560, 1400), QSize(1280, 720));
        QCOMPARE(fitVideoWindowSize(3840, 2160, 2560, 1400), QSize(2240, 1260));
        QCOMPARE(fitVideoWindowSize(720, 300, 1920, 1040), QSize(864, 360));
        QCOMPARE(fitVideoWindowSize(640, 480, 1920, 1040), QSize(640, 480));
        QCOMPARE(fitVideoWindowSize(1920, 1080, 2048, 1080, 0.9, 640, 360, 2.0), QSize(960, 540));
        QCOMPARE(fitVideoWindowSize(0, 1080, 1920, 1040), QSize());
        QCOMPARE(fitVideoWindowSize(1920, 1080, 1920, 1040, 0.9, 640, 360, 0.0), QSize());
    }

};

QTEST_APPLESS_MAIN(PlayerStateTest)
#include "test_player_state.moc"
