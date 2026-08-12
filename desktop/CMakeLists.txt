cmake_minimum_required(VERSION 3.21)

project(AutoAnimeDesktopProbe VERSION 0.1.0 LANGUAGES CXX)

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
    src/player/PlayerController.cpp
    src/player/PlayerController.h
    src/system/SleepInhibitor.cpp
    src/system/SleepInhibitor.h
    src/player/MpvVideoItem.cpp
    src/player/MpvVideoItem.h
    src/qml/QmlBackend.cpp
    src/qml/QmlBackend.h
    src/qml/QmlPlayer.cpp
    src/qml/QmlPlayer.h
)
qt_add_qml_module(autoanime-desktop
    URI AutoAnime
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/HomePage.qml
        qml/SubjectsPage.qml
        qml/SubjectDetailPage.qml
        qml/PlayerPage.qml
        qml/LibraryPage.qml
        qml/DownloadsPage.qml
        qml/SettingsPage.qml
        qml/MediaCard.qml
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
endif()
