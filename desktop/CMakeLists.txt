cmake_minimum_required(VERSION 3.21)

project(AutoAnime VERSION 0.2.1 LANGUAGES CXX)

include(GNUInstallDirs)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)

include(CTest)
find_package(PkgConfig REQUIRED)
find_package(Qt6 6.4 REQUIRED COMPONENTS Core DBus Gui Network Qml Quick QuickControls2)
pkg_check_modules(MPV QUIET IMPORTED_TARGET mpv)
if(TARGET PkgConfig::MPV)
    set(AUTOANIME_MPV_TARGET PkgConfig::MPV)
else()
    find_path(MPV_INCLUDE_DIR REQUIRED NAMES mpv/client.h)
    find_library(MPV_LIBRARY REQUIRED NAMES mpv)
    add_library(AutoAnimeMpv UNKNOWN IMPORTED)
    set_target_properties(AutoAnimeMpv PROPERTIES
        IMPORTED_LOCATION "${MPV_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${MPV_INCLUDE_DIR}"
    )
    set(AUTOANIME_MPV_TARGET AutoAnimeMpv)
endif()

add_library(autoanime_player STATIC
    src/player/MpvCore.cpp
    src/player/MpvCore.h
    src/player/PlayerState.h
)
target_include_directories(autoanime_player PUBLIC src)
target_link_libraries(autoanime_player
    PUBLIC
        Qt6::Core
        Qt6::Gui
        ${AUTOANIME_MPV_TARGET}
)
target_compile_options(autoanime_player PRIVATE -Wall -Wextra -Wpedantic)

qt_add_executable(autoanime-desktop
    src/main_qml.cpp
    src/backend/BackendClient.cpp
    src/backend/BackendClient.h
    src/backend/BackendSupervisor.cpp
    src/backend/BackendSupervisor.h
    src/player/PlayerController.cpp
    src/player/PlayerController.h
    src/system/SleepInhibitor.cpp
    src/system/SleepInhibitor.h
    src/system/NetworkProxy.cpp
    src/system/NetworkProxy.h
    src/player/MpvVideoItem.cpp
    src/player/MpvVideoItem.h
    src/qml/QmlBackend.cpp
    src/qml/QmlBackend.h
    src/qml/DesktopPreferences.cpp
    src/qml/DesktopPreferences.h
    src/qml/QmlPlayer.cpp
    src/qml/QmlPlayer.h
    src/qml/RoundedCornerMaskItem.cpp
    src/qml/RoundedCornerMaskItem.h
)
set_source_files_properties(
    qml/theme/Theme.qml
    qml/theme/Typography.qml
    qml/theme/Metrics.qml
    PROPERTIES QT_QML_SINGLETON_TYPE TRUE
)
qt_add_qml_module(autoanime-desktop
    URI AutoAnime
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/StartupError.qml
        qml/HomePage.qml
        qml/SubjectsPage.qml
        qml/SubjectDetailPage.qml
        qml/PlayerPage.qml
        qml/LibraryPage.qml
        qml/DownloadsPage.qml
        qml/QuarantinePage.qml
        qml/SettingsPage.qml
        qml/theme/Theme.qml
        qml/theme/Typography.qml
        qml/theme/Metrics.qml
        qml/components/AppButton.qml
        qml/components/AppProgressBar.qml
        qml/components/PlayerSlider.qml
        qml/components/IconButton.qml
        qml/components/RoundedImage.qml
        qml/components/SectionHeader.qml
        qml/components/MediaCard.qml
        qml/components/EpisodeRow.qml
        qml/components/StatusBadge.qml
        qml/components/EmptyState.qml
        qml/components/SettingsSection.qml
        qml/components/AppTab.qml
    RESOURCES
        qml/icons/LUCIDE_LICENSE.txt
        qml/icons/house.svg
        qml/icons/library-big.svg
        qml/icons/folder-search.svg
        qml/icons/download.svg
        qml/icons/archive-restore.svg
        qml/icons/settings.svg
        qml/icons/play.svg
        qml/icons/pause.svg
        qml/icons/skip-back.svg
        qml/icons/skip-forward.svg
        qml/icons/volume-2.svg
        qml/icons/volume-x.svg
        qml/icons/captions.svg
        qml/icons/audio-lines.svg
        qml/icons/maximize.svg
        qml/icons/arrow-left.svg
        qml/icons/refresh-cw.svg
        qml/icons/scan-search.svg
        qml/icons/search.svg
        qml/icons/more-horizontal.svg
        qml/icons/image.svg
        qml/icons/inbox.svg
        qml/icons/x.svg
        qml/icons/trash-2.svg
        qml/icons/shield-alert.svg
        qml/icons/rotate-ccw.svg
)
target_include_directories(autoanime-desktop PRIVATE src)
target_link_libraries(autoanime-desktop
    PRIVATE
        autoanime_player
        Qt6::Network
        Qt6::DBus
        Qt6::Qml
        Qt6::Quick
        Qt6::QuickControls2
)
target_compile_options(autoanime-desktop PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(autoanime-desktop PRIVATE AUTOANIME_VERSION="${PROJECT_VERSION}")

if(BUILD_TESTING)
    find_package(Qt6 6.4 REQUIRED COMPONENTS Test)
    add_executable(autoanime-player-state-tests tests/test_player_state.cpp)
    target_link_libraries(autoanime-player-state-tests PRIVATE autoanime_player Qt6::Test)
    add_test(NAME autoanime-player-state-tests COMMAND autoanime-player-state-tests)

    add_executable(autoanime-player-controller-activity-tests
        tests/test_player_controller_activity.cpp
        src/backend/BackendClient.cpp
        src/backend/BackendClient.h
        src/player/PlayerController.cpp
        src/player/PlayerController.h
    )
    target_include_directories(autoanime-player-controller-activity-tests PRIVATE src)
    target_link_libraries(
        autoanime-player-controller-activity-tests
        PRIVATE autoanime_player Qt6::Network Qt6::Test
    )
    target_compile_options(autoanime-player-controller-activity-tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(
        NAME autoanime-player-controller-activity-tests
        COMMAND autoanime-player-controller-activity-tests
    )

    add_executable(autoanime-sleep-inhibitor-tests
        tests/test_sleep_inhibitor.cpp
        src/system/SleepInhibitor.cpp
        src/system/SleepInhibitor.h
    )
    target_include_directories(autoanime-sleep-inhibitor-tests PRIVATE src)
    target_link_libraries(autoanime-sleep-inhibitor-tests PRIVATE Qt6::Core Qt6::DBus Qt6::Test)
    target_compile_options(autoanime-sleep-inhibitor-tests PRIVATE -Wall -Wextra -Wpedantic)
    find_program(DBUS_RUN_SESSION_EXECUTABLE dbus-run-session)
    if(DBUS_RUN_SESSION_EXECUTABLE)
        add_test(
            NAME autoanime-sleep-inhibitor-tests
            COMMAND ${DBUS_RUN_SESSION_EXECUTABLE} -- $<TARGET_FILE:autoanime-sleep-inhibitor-tests>
        )
    else()
        add_test(NAME autoanime-sleep-inhibitor-tests COMMAND autoanime-sleep-inhibitor-tests)
    endif()

    add_executable(autoanime-qml-backend-activity-tests
        tests/test_qml_backend_activity.cpp
        src/qml/QmlBackend.cpp
        src/qml/QmlBackend.h
    )
    target_include_directories(autoanime-qml-backend-activity-tests PRIVATE src)
    target_link_libraries(
        autoanime-qml-backend-activity-tests
        PRIVATE Qt6::Core Qt6::Network Qt6::Test
    )
    target_compile_options(autoanime-qml-backend-activity-tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(
        NAME autoanime-qml-backend-activity-tests
        COMMAND autoanime-qml-backend-activity-tests
    )

    add_executable(autoanime-network-proxy-tests
        tests/test_network_proxy.cpp
        src/system/NetworkProxy.cpp
        src/system/NetworkProxy.h
    )
    target_include_directories(autoanime-network-proxy-tests PRIVATE src)
    target_link_libraries(autoanime-network-proxy-tests PRIVATE Qt6::Network Qt6::Test)
    target_compile_options(autoanime-network-proxy-tests PRIVATE -Wall -Wextra -Wpedantic)
    add_test(
        NAME autoanime-network-proxy-tests
        COMMAND autoanime-network-proxy-tests
    )
endif()

# Ubuntu is the first supported release platform. The package keeps qBittorrent
# external, but carries the backend source, migrations and the repository venv
# so launching the desktop entry does not require uvicorn/cmake/terminal setup.
set(AUTOANIME_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
install(TARGETS autoanime-desktop RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")
install(
    DIRECTORY "${AUTOANIME_ROOT}/backend"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/autoanime"
    PATTERN "__pycache__" EXCLUDE
    PATTERN "*.pyc" EXCLUDE
)
install(
    DIRECTORY "${AUTOANIME_ROOT}/scripts"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/autoanime"
    FILES_MATCHING PATTERN "*.py"
)
install(
    FILES
        "${AUTOANIME_ROOT}/alembic.ini"
        "${AUTOANIME_ROOT}/config.example.yaml"
        "${AUTOANIME_ROOT}/pyproject.toml"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/autoanime"
)
if(EXISTS "${AUTOANIME_ROOT}/.venv/bin/python3")
    install(
        DIRECTORY "${AUTOANIME_ROOT}/.venv/"
        DESTINATION "${CMAKE_INSTALL_LIBDIR}/autoanime/venv"
        PATTERN "__pycache__" EXCLUDE
        PATTERN "*.pyc" EXCLUDE
        PATTERN "*.pyo" EXCLUDE
    )
else()
    message(WARNING "Repository .venv not found; the package will require AUTOANIME_PYTHON")
endif()
install(
    FILES packaging/autoanime.desktop
    DESTINATION "${CMAKE_INSTALL_DATADIR}/applications"
)
install(
    FILES qml/icons/library-big.svg
    DESTINATION "${CMAKE_INSTALL_DATADIR}/icons/hicolor/scalable/apps"
    RENAME autoanime.svg
)

set(CPACK_PACKAGE_NAME "AutoAnime")
set(CPACK_PACKAGE_VENDOR "AutoAnime")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "本地动画媒体库与自动追番客户端")
set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
set(CPACK_PACKAGE_CONTACT "ch-yu02")
set(CPACK_RESOURCE_FILE_LICENSE "${AUTOANIME_ROOT}/desktop/THIRD_PARTY_NOTICES.md")
set(CPACK_GENERATOR "DEB;TGZ")
set(CPACK_DEBIAN_FILE_NAME DEB-DEFAULT)
set(CPACK_DEBIAN_PACKAGE_SHLIBDEPS ON)
set(CPACK_DEBIAN_PACKAGE_DEPENDS "python3 (>= 3.12), libmpv2, ffmpeg, qml6-module-qtqml, qml6-module-qtqml-workerscript, qml6-module-qtquick, qml6-module-qtquick-window, qml6-module-qtquick-templates, qml6-module-qtquick-controls, qml6-module-qtquick-layouts, qml6-module-qtquick-dialogs")
include(CPack)
