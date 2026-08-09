#include "player/PlayerState.h"

#include <QTest>

using autoanime::MediaTrack;
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

};

QTEST_APPLESS_MAIN(PlayerStateTest)
#include "test_player_state.moc"
