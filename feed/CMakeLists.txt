add_library(microprice_feed STATIC src/multicast.cpp)
add_library(microprice::feed ALIAS microprice_feed)
target_include_directories(microprice_feed PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(microprice_feed PUBLIC microprice::engine PRIVATE microprice_warnings)

find_package(Threads REQUIRED)

add_executable(feed_replay src/feed_replay.cpp)
target_link_libraries(feed_replay PRIVATE microprice::feed microprice_warnings)

add_executable(feed_capture src/feed_capture.cpp)
target_link_libraries(feed_capture PRIVATE microprice::feed microprice_warnings Threads::Threads)

if(MICROPRICE_BUILD_TESTS)
  add_executable(feed_tests tests/wire_test.cpp tests/spsc_ring_test.cpp tests/lobster_test.cpp tests/multicast_test.cpp)
  target_link_libraries(feed_tests PRIVATE microprice::feed microprice_warnings Threads::Threads GTest::gtest_main)
  gtest_discover_tests(feed_tests)
endif()
