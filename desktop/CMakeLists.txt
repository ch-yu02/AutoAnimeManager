cmake_minimum_required(VERSION 3.21)

project(AutoAnimeDesktopProbe VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)

include(CTest)
find_package(PkgConfig REQUIRED)
find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Widgets OpenGLWidgets)
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
    src/player/MpvRenderWidget.cpp
    src/player/MpvRenderWidget.h
    src/player/PlayerState.h
)
target_include_directories(autoanime_player PUBLIC src)
target_link_libraries(autoanime_player
    PUBLIC
        Qt6::Core
        Qt6::Gui
        Qt6::Widgets
        Qt6::OpenGLWidgets
        ${AUTOANIME_MPV_TARGET}
)
target_compile_options(autoanime_player PRIVATE -Wall -Wextra -Wpedantic)

add_executable(autoanime-player-probe
    src/main.cpp
    src/ui/PlayerWindow.cpp
    src/ui/PlayerWindow.h
)
target_link_libraries(autoanime-player-probe PRIVATE autoanime_player)

find_package(Qt6 6.4 REQUIRED COMPONENTS Network WebChannel WebEngineWidgets)
add_executable(autoanime-desktop
    src/main_desktop.cpp
    src/backend/BackendClient.cpp
    src/backend/BackendClient.h
    src/bridge/NativeBridge.cpp
    src/bridge/NativeBridge.h
    src/player/PlayerController.cpp
    src/player/PlayerController.h
    src/ui/AppWebPage.cpp
    src/ui/AppWebPage.h
    src/ui/DesktopWindow.cpp
    src/ui/DesktopWindow.h
    src/ui/PlayerSurfaceGeometry.h
)
target_include_directories(autoanime-desktop PRIVATE src)
target_link_libraries(autoanime-desktop
    PRIVATE
        autoanime_player
        Qt6::Network
        Qt6::WebChannel
        Qt6::WebEngineWidgets
)
target_compile_options(autoanime-desktop PRIVATE -Wall -Wextra -Wpedantic)

if(BUILD_TESTING)
    find_package(Qt6 6.4 REQUIRED COMPONENTS Test)
    add_executable(autoanime-player-state-tests tests/test_player_state.cpp)
    target_link_libraries(autoanime-player-state-tests PRIVATE autoanime_player Qt6::Test)
    add_test(NAME autoanime-player-state-tests COMMAND autoanime-player-state-tests)
endif()
