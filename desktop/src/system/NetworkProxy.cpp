#include "system/NetworkProxy.h"

#include <QDebug>
#include <QUrl>

namespace autoanime {
namespace {

QByteArray firstProxyEnvironmentValue()
{
    // Match HTTPX's documented proxy environment contract so Qt poster loads
    // and backend Bangumi calls use the same user-selected proxy.
    // Source: https://www.python-httpx.org/environment_variables/#proxies
    static constexpr const char *names[] = {
        "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
    };
    for (const char *name : names) {
        const QByteArray value = qgetenv(name).trimmed();
        if (!value.isEmpty()) {
            return value;
        }
    }
    return {};
}

} // namespace

QNetworkProxy networkProxyFromEnvironment()
{
    const QByteArray rawValue = firstProxyEnvironmentValue();
    if (rawValue.isEmpty()) {
        return QNetworkProxy(QNetworkProxy::NoProxy);
    }

    const QUrl url = QUrl::fromEncoded(rawValue);
    const QString scheme = url.scheme().toLower();
    QNetworkProxy::ProxyType type = QNetworkProxy::NoProxy;
    quint16 defaultPort = 0;
    if (scheme == QStringLiteral("http") || scheme == QStringLiteral("https")) {
        type = QNetworkProxy::HttpProxy;
        defaultPort = 80;
    } else if (scheme == QStringLiteral("socks5") || scheme == QStringLiteral("socks5h")) {
        type = QNetworkProxy::Socks5Proxy;
        defaultPort = 1080;
    }
    if (type == QNetworkProxy::NoProxy || url.host().isEmpty()) {
        qWarning("忽略无效或不支持的网络代理配置");
        return QNetworkProxy(QNetworkProxy::NoProxy);
    }

    const int configuredPort = url.port(defaultPort);
    if (configuredPort < 1 || configuredPort > 65535) {
        qWarning("忽略端口无效的网络代理配置");
        return QNetworkProxy(QNetworkProxy::NoProxy);
    }
    return QNetworkProxy(
        type,
        url.host(),
        static_cast<quint16>(configuredPort),
        QUrl::fromPercentEncoding(url.userName(QUrl::FullyEncoded).toUtf8()),
        QUrl::fromPercentEncoding(url.password(QUrl::FullyEncoded).toUtf8())
    );
}

void configureApplicationNetworkProxy()
{
    // QNetworkProxy's application proxy applies to QNetworkAccessManager,
    // including the manager used internally by Qt Quick Image.
    // Source: https://doc.qt.io/qt-6/qnetworkproxy.html#detailed-description
    const QNetworkProxy proxy = networkProxyFromEnvironment();
    QNetworkProxy::setApplicationProxy(proxy);
    if (proxy.type() == QNetworkProxy::NoProxy) {
        qInfo("Qt 外部网络：直连");
    } else {
        qInfo("Qt 外部网络：使用代理 %s:%u", qPrintable(proxy.hostName()), proxy.port());
    }
}

} // namespace autoanime
