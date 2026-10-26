add_library(microprice_engine INTERFACE)
add_library(microprice::engine ALIAS microprice_engine)
target_include_directories(microprice_engine INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(microprice_engine INTERFACE cxx_std_20)

if(MICROPRICE_BUILD_TESTS)
  add_executable(engine_tests
    tests/order_book_test.cpp
    tests/id_map_test.cpp
    tests/differential_test.cpp)
  target_link_libraries(engine_tests PRIVATE microprice::engine microprice_warnings GTest::gtest_main)
  gtest_discover_tests(engine_tests)
endif()

if(MICROPRICE_BUILD_BENCH)
  add_executable(engine_bench bench/order_book_bench.cpp)
  target_link_libraries(engine_bench PRIVATE microprice::engine benchmark::benchmark)
endif()
