#include "player/MpvCore.h"

#include <mpv/client.h>

#include <QByteArray>
#include <QMetaObject>

#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace autoanime {
namespace {

const mpv_node *mapValue(const mpv_node &node, const char *key)
{
    if (node.format != MPV_FORMAT_NODE_MAP || node.u.list == nullptr) {
        return nullptr;
    }
    for (int index = 0; index < node.u.list->num; ++index) {
        if (std::strcmp(node.u.list->keys[index], key) == 0) {
            return &node.u.list->values[index];
        }
    }
    return nullptr;
}

QString nodeString(const mpv_node &node, const char *key)
{
    const mpv_node *value = mapValue(node, key);
    return value != nullptr && value->format == MPV_FORMAT_STRING && value->u.string != nullptr
        ? QString::fromUtf8(value->u.string)
        : QString{};
}

int nodeInteger(const mpv_node &node, const char *key, int fallback = -1)
{
    const mpv_node *value = mapValue(node, key);
    return value != nullptr && value->format == MPV_FORMAT_INT64
        ? static_cast<int>(value->u.int64)
        : fallback;
}

bool nodeFlag(const mpv_node &node, const char *key)
{
    const mpv_node *value = mapValue(node, key);
    return value != nullptr && value->format == MPV_FORMAT_FLAG && value->u.flag != 0;
}

} // namespace

MpvCore::MpvCore(QObject *parent)
    : QObject(parent)
    , m_handle(mpv_create())
{
    if (m_handle == nullptr) {
        throw std::runtime_error("无法创建 libmpv context");
    }

    mpv_set_option_string(m_handle, "vo", "libmpv");
    mpv_set_option_string(m_handle, "terminal", "no");
    mpv_set_option_string(m_handle, "osc", "no");
    mpv_set_option_string(m_handle, "input-default-bindings", "no");
    mpv_set_option_string(m_handle, "keep-open", "no");
    mpv_set_option_string(m_handle, "hwdec", "auto-safe");
    mpv_set_option_string(m_handle, "audio-display", "no");

    const int result = mpv_initialize(m_handle);
    if (result < 0) {
        const QString message = QStringLiteral("无法初始化 libmpv：%1")
            .arg(QString::fromUtf8(mpv_error_string(result)));
        mpv_terminate_destroy(m_handle);
        m_handle = nullptr;
        throw std::runtime_error(message.toStdString());
    }

    mpv_request_log_messages(m_handle, "warn");
    observeProperties();
    mpv_set_wakeup_callback(m_handle, &MpvCore::wakeup, this);
}

MpvCore::~MpvCore()
{
    shutdown();
}

void MpvCore::loadFile(const QString &path)
{
    if (m_videoWidth != 0 || m_videoHeight != 0) {
        m_videoWidth = 0;
        m_videoHeight = 0;
        emit videoSizeChanged(0, 0);
    }
    m_requestedPath = path;
    command({QStringLiteral("loadfile"), path, QStringLiteral("replace")});
}

void MpvCore::setPaused(bool paused)
{
    reportError(QStringLiteral("设置暂停状态"), setFlag("pause", paused));
}

void MpvCore::togglePause()
{
    setPaused(!m_paused);
}

void MpvCore::seekAbsolute(double seconds)
{
    command({QStringLiteral("seek"), QString::number(std::max(0.0, seconds), 'f', 3), QStringLiteral("absolute+exact")});
}

void MpvCore::seekRelative(double seconds)
{
    command({QStringLiteral("seek"), QString::number(seconds, 'f', 3), QStringLiteral("relative+exact")});
}

void MpvCore::setVolume(double value)
{
    reportError(QStringLiteral("设置音量"), setDouble("volume", std::clamp(value, 0.0, 100.0)));
}

void MpvCore::setMuted(bool muted)
{
    reportError(QStringLiteral("设置静音"), setFlag("mute", muted));
}

void MpvCore::setSpeed(double value)
{
    reportError(QStringLiteral("设置播放速度"), setDouble("speed", std::clamp(value, 0.25, 4.0)));
}

void MpvCore::selectAudioTrack(int id)
{
    reportError(QStringLiteral("选择音轨"), id < 0
        ? setString("aid", QStringLiteral("no"))
        : setString("aid", QString::number(id)));
}

void MpvCore::selectSubtitleTrack(int id)
{
    reportError(QStringLiteral("选择字幕"), id < 0
        ? setString("sid", QStringLiteral("no"))
        : setString("sid", QString::number(id)));
}

void MpvCore::addSubtitle(const QString &path)
{
    command({QStringLiteral("sub-add"), path, QStringLiteral("select")});
}

void MpvCore::stop()
{
    command({QStringLiteral("stop")});
}

void MpvCore::shutdown()
{
    if (m_handle == nullptr) {
        return;
    }
    mpv_set_wakeup_callback(m_handle, nullptr, nullptr);
    mpv_terminate_destroy(m_handle);
    m_handle = nullptr;
}

void MpvCore::processEvents()
{
    while (m_handle != nullptr) {
        mpv_event *event = mpv_wait_event(m_handle, 0);
        if (event == nullptr || event->event_id == MPV_EVENT_NONE) {
            break;
        }
        handleEvent(event);
    }
}

void MpvCore::wakeup(void *context)
{
    auto *core = static_cast<MpvCore *>(context);
    QMetaObject::invokeMethod(core, &MpvCore::processEvents, Qt::QueuedConnection);
}

void MpvCore::handleEvent(mpv_event *event)
{
    switch (event->event_id) {
    case MPV_EVENT_FILE_LOADED:
        refreshTrackList();
        emit fileLoaded(m_requestedPath);
        break;
    case MPV_EVENT_END_FILE: {
        const auto *end = static_cast<mpv_event_end_file *>(event->data);
        const QString detail = end != nullptr && end->error < 0
            ? QString::fromUtf8(mpv_error_string(end->error))
            : QString{};
        emit endFile(end == nullptr ? -1 : end->reason, detail);
        break;
    }
    case MPV_EVENT_PROPERTY_CHANGE: {
        const auto *property = static_cast<mpv_event_property *>(event->data);
        if (property == nullptr || property->name == nullptr) {
            break;
        }
        if (std::strcmp(property->name, "time-pos") == 0 && property->format == MPV_FORMAT_DOUBLE && property->data != nullptr) {
            m_position = *static_cast<double *>(property->data);
            emit positionChanged(m_position);
        } else if (std::strcmp(property->name, "duration") == 0 && property->format == MPV_FORMAT_DOUBLE && property->data != nullptr) {
            m_duration = *static_cast<double *>(property->data);
            emit durationChanged(m_duration);
        } else if (std::strcmp(property->name, "pause") == 0 && property->format == MPV_FORMAT_FLAG && property->data != nullptr) {
            m_paused = *static_cast<int *>(property->data) != 0;
            emit pauseChanged(m_paused);
        } else if (std::strcmp(property->name, "volume") == 0 && property->format == MPV_FORMAT_DOUBLE && property->data != nullptr) {
            m_volume = *static_cast<double *>(property->data);
            emit volumeChanged(m_volume);
        } else if (std::strcmp(property->name, "mute") == 0 && property->format == MPV_FORMAT_FLAG && property->data != nullptr) {
            m_muted = *static_cast<int *>(property->data) != 0;
            emit muteChanged(m_muted);
        } else if (std::strcmp(property->name, "speed") == 0 && property->format == MPV_FORMAT_DOUBLE && property->data != nullptr) {
            m_speed = *static_cast<double *>(property->data);
            emit speedChanged(m_speed);
        } else if (std::strcmp(property->name, "decoder-frame-drop-count") == 0 && property->format == MPV_FORMAT_INT64 && property->data != nullptr) {
            m_droppedFrames = *static_cast<qint64 *>(property->data);
            emit diagnosticsChanged(m_hwdec, m_droppedFrames);
        } else if (std::strcmp(property->name, "hwdec-current") == 0 && property->format == MPV_FORMAT_STRING && property->data != nullptr) {
            const char *value = *static_cast<char **>(property->data);
            m_hwdec = value == nullptr ? QString{} : QString::fromUtf8(value);
            emit diagnosticsChanged(m_hwdec, m_droppedFrames);
        } else if (std::strcmp(property->name, "video-params") == 0
                   && property->format == MPV_FORMAT_NODE && property->data != nullptr) {
            const auto &parameters = *static_cast<mpv_node *>(property->data);
            const int width = nodeInteger(parameters, "dw", nodeInteger(parameters, "w", 0));
            const int height = nodeInteger(parameters, "dh", nodeInteger(parameters, "h", 0));
            if (width > 0 && height > 0
                && (width != m_videoWidth || height != m_videoHeight)) {
                m_videoWidth = width;
                m_videoHeight = height;
                emit videoSizeChanged(width, height);
            }
        } else if (std::strcmp(property->name, "track-list") == 0 && property->format == MPV_FORMAT_NODE && property->data != nullptr) {
            refreshTrackList();
        } else if (std::strcmp(property->name, "aid") == 0 || std::strcmp(property->name, "sid") == 0) {
            refreshTrackList();
        }
        break;
    }
    case MPV_EVENT_COMMAND_REPLY:
        if (event->error < 0) {
            reportError(QStringLiteral("执行播放器命令"), event->error);
        }
        break;
    case MPV_EVENT_LOG_MESSAGE: {
        const auto *log = static_cast<mpv_event_log_message *>(event->data);
        if (log != nullptr && log->text != nullptr) {
            emit logMessage(QString::fromUtf8(log->text).trimmed());
        }
        break;
    }
    case MPV_EVENT_SHUTDOWN:
        emit shutdownRequested();
        break;
    default:
        break;
    }
}

void MpvCore::observeProperties()
{
    mpv_observe_property(m_handle, 1, "time-pos", MPV_FORMAT_DOUBLE);
    mpv_observe_property(m_handle, 2, "duration", MPV_FORMAT_DOUBLE);
    mpv_observe_property(m_handle, 3, "pause", MPV_FORMAT_FLAG);
    mpv_observe_property(m_handle, 4, "volume", MPV_FORMAT_DOUBLE);
    mpv_observe_property(m_handle, 5, "mute", MPV_FORMAT_FLAG);
    mpv_observe_property(m_handle, 6, "track-list", MPV_FORMAT_NODE);
    mpv_observe_property(m_handle, 7, "aid", MPV_FORMAT_NODE);
    mpv_observe_property(m_handle, 8, "sid", MPV_FORMAT_NODE);
    mpv_observe_property(m_handle, 9, "speed", MPV_FORMAT_DOUBLE);
    mpv_observe_property(m_handle, 10, "decoder-frame-drop-count", MPV_FORMAT_INT64);
    mpv_observe_property(m_handle, 11, "hwdec-current", MPV_FORMAT_STRING);
    mpv_observe_property(m_handle, 12, "video-params", MPV_FORMAT_NODE);
}

void MpvCore::refreshTrackList()
{
    if (m_handle == nullptr) {
        return;
    }
    mpv_node root{};
    const int result = mpv_get_property(m_handle, "track-list", MPV_FORMAT_NODE, &root);
    if (result < 0) {
        return;
    }

    QList<MediaTrack> tracks;
    if (root.format == MPV_FORMAT_NODE_ARRAY && root.u.list != nullptr) {
        tracks.reserve(root.u.list->num);
        for (int index = 0; index < root.u.list->num; ++index) {
            const mpv_node &node = root.u.list->values[index];
            MediaTrack track;
            track.id = nodeInteger(node, "id");
            track.type = nodeString(node, "type");
            track.title = nodeString(node, "title");
            track.language = nodeString(node, "lang");
            track.codec = nodeString(node, "codec");
            track.selected = nodeFlag(node, "selected");
            track.external = nodeFlag(node, "external");
            if (track.id >= 0 && !track.type.isEmpty()) {
                tracks.append(track);
            }
        }
    }
    mpv_free_node_contents(&root);
    emit trackListChanged(tracks);
}

int MpvCore::command(const QStringList &arguments)
{
    if (m_handle == nullptr || arguments.isEmpty()) {
        return MPV_ERROR_UNINITIALIZED;
    }
    std::vector<QByteArray> encoded;
    encoded.reserve(static_cast<std::size_t>(arguments.size()));
    for (const QString &argument : arguments) {
        encoded.emplace_back(argument.toUtf8());
    }
    std::vector<const char *> values;
    values.reserve(encoded.size() + 1);
    for (const QByteArray &argument : encoded) {
        values.push_back(argument.constData());
    }
    values.push_back(nullptr);
    const int result = mpv_command_async(m_handle, m_requestId++, values.data());
    reportError(arguments.first(), result);
    return result;
}

int MpvCore::setFlag(const char *name, bool value)
{
    int flag = value ? 1 : 0;
    return m_handle == nullptr
        ? MPV_ERROR_UNINITIALIZED
        : mpv_set_property(m_handle, name, MPV_FORMAT_FLAG, &flag);
}

int MpvCore::setDouble(const char *name, double value)
{
    return m_handle == nullptr
        ? MPV_ERROR_UNINITIALIZED
        : mpv_set_property(m_handle, name, MPV_FORMAT_DOUBLE, &value);
}

int MpvCore::setString(const char *name, const QString &value)
{
    const QByteArray encoded = value.toUtf8();
    const char *raw = encoded.constData();
    return m_handle == nullptr
        ? MPV_ERROR_UNINITIALIZED
        : mpv_set_property(m_handle, name, MPV_FORMAT_STRING, &raw);
}

void MpvCore::reportError(const QString &operation, int errorCode)
{
    if (errorCode < 0) {
        emit playbackError(QStringLiteral("%1失败：%2")
            .arg(operation, QString::fromUtf8(mpv_error_string(errorCode))));
    }
}

} // namespace autoanime
