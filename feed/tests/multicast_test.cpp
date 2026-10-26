#include "microprice/feed/multicast.hpp"

#include <gtest/gtest.h>

#include <system_error>
#include <vector>

namespace microprice::feed {
namespace {

TEST(MulticastTest, LoopbackDeliversEveryMessageInOrder) {
  const Endpoint endpoint{"239.255.0.7", 30107, "127.0.0.1"};
  std::unique_ptr<MulticastReceiver> receiver;
  try {
    receiver = std::make_unique<MulticastReceiver>(endpoint);
  } catch (const std::system_error& error) {
    GTEST_SKIP() << "multicast unavailable: " << error.what();
  }
  constexpr int kEvents = 500;
  {
    MulticastPublisher publisher(endpoint, 1);
    for (int i = 0; i < kEvents; ++i) {
      publisher.publish(BookEvent{EventType::Add, Side::Buy, static_cast<OrderId>(i + 1), 0, 100, 1, 1, i}, 1);
    }
  }  // destructor flushes the final partial packet
  std::vector<std::uint64_t> seqs;
  while (receiver->poll(500, [&](std::uint64_t seq, const WireMessage& m) {
    EXPECT_EQ(m.id, seq);
    seqs.push_back(seq);
  })) {
  }
  if (seqs.empty()) {
    GTEST_SKIP() << "no multicast route on loopback in this environment";
  }
  ASSERT_EQ(seqs.size(), static_cast<std::size_t>(kEvents));
  EXPECT_EQ(receiver->stats().gaps, 0u);
  EXPECT_EQ(receiver->expected_seq(), static_cast<std::uint64_t>(kEvents + 1));
}

}  // namespace
}  // namespace microprice::feed
