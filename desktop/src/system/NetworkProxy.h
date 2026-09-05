#pragma once

#include <QNetworkProxy>

namespace autoanime {

QNetworkProxy networkProxyFromEnvironment();
void configureApplicationNetworkProxy();

} // namespace autoanime
