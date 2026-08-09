#include "ui/AppWebPage.h"

#include <QDesktopServices>

#include <utility>

namespace autoanime {

AppWebPage::AppWebPage(QUrl trustedFrontendUrl, QObject *parent)
    : QWebEnginePage(parent)
    , m_trustedFrontendUrl(std::move(trustedFrontendUrl))
{
}

bool AppWebPage::isTrustedOrigin(const QUrl &url) const
{
    if (url.scheme() == QStringLiteral("qrc")) {
        return true;
    }
    return url.scheme().compare(m_trustedFrontendUrl.scheme(), Qt::CaseInsensitive) == 0
        && url.host().compare(m_trustedFrontendUrl.host(), Qt::CaseInsensitive) == 0
        && url.port(url.scheme() == QStringLiteral("https") ? 443 : 80)
            == m_trustedFrontendUrl.port(
                m_trustedFrontendUrl.scheme() == QStringLiteral("https") ? 443 : 80
            );
}

bool AppWebPage::acceptNavigationRequest(const QUrl &url, NavigationType type, bool isMainFrame)
{
    if (isTrustedOrigin(url)) {
        return QWebEnginePage::acceptNavigationRequest(url, type, isMainFrame);
    }
    if (isMainFrame && (url.scheme() == QStringLiteral("http") || url.scheme() == QStringLiteral("https"))) {
        QDesktopServices::openUrl(url);
    }
    return false;
}

} // namespace autoanime
