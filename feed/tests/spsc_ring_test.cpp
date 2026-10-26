#include "microprice/feed/spsc_ring.hpp"

#include <gtest/gtest.h>

#include <cstdint>
#include <memory>
#include <thread>

namespace microprice::feed {
namespace {

TEST(SpscRingTest, FillsToCapacityThenRejects) {
  SpscRing<int, 4> ring;
  for (int i = 0; i < 4; ++i) {
    EXPECT_TRUE(ring.try_push(i));
  }
  EXPECT_FALSE(ring.try_push(99));
  EXPECT_EQ(ring.try_pop(), 0);
  EXPECT_TRUE(ring.try_push(4));
  for (int expected = 1; expected <= 4; ++expected) {
    EXPECT_EQ(ring.try_pop(), expected);
  }
  EXPECT_FALSE(ring.try_pop().has_value());
}

TEST(SpscRingTest, PreservesOrderAcrossThreads) {
  constexpr std::uint64_t kCount = 5'000'000;
  auto ring = std::make_unique<SpscRing<std::uint64_t, 1024>>();
  std::thread producer([&] {
    for (std::uint64_t i = 0; i < kCount; ++i) {
      while (!ring->try_push(i)) {
      }
    }
  });
  std::uint64_t expected = 0;
  while (expected < kCount) {
    if (const auto value = ring->try_pop()) {
      ASSERT_EQ(*value, expected);
      ++expected;
    }
  }
  producer.join();
}

TEST(SpscRingTest, IndicesLiveOnSeparateCacheLines) {
  EXPECT_GE(sizeof(SpscRing<int, 2>), 4 * kCacheLine);
}

}  // namespace
}  // namespace microprice::feed
