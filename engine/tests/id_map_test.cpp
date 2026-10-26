#include "microprice/id_map.hpp"

#include <gtest/gtest.h>

#include <random>
#include <unordered_map>

namespace microprice {
namespace {

TEST(IdMapTest, InsertFindErase) {
  IdMap map(8);
  EXPECT_TRUE(map.insert(42, 7));
  EXPECT_FALSE(map.insert(42, 8));
  EXPECT_EQ(map.find(42), 7u);
  EXPECT_TRUE(map.erase(42));
  EXPECT_EQ(map.find(42), kNil);
  EXPECT_FALSE(map.erase(42));
}

TEST(IdMapTest, MatchesStandardMapUnderRandomChurn) {
  constexpr std::uint32_t kCapacity = 4096;
  IdMap map(kCapacity);
  std::unordered_map<OrderId, NodeIndex> reference;
  std::mt19937_64 rng(7);
  for (int step = 0; step < 200'000; ++step) {
    const OrderId id = rng() % 8192;
    if (rng() % 2 == 0 && reference.size() < kCapacity) {
      const auto value = static_cast<NodeIndex>(rng() % 1000);
      EXPECT_EQ(map.insert(id, value), reference.emplace(id, value).second);
    } else {
      EXPECT_EQ(map.erase(id), reference.erase(id) == 1);
    }
    const OrderId probe = rng() % 8192;
    const auto it = reference.find(probe);
    EXPECT_EQ(map.find(probe), it == reference.end() ? kNil : it->second);
  }
  EXPECT_EQ(map.size(), reference.size());
}

}  // namespace
}  // namespace microprice
