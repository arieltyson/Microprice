#include "microprice/feed/wire.hpp"

#include <gtest/gtest.h>

#include <vector>

namespace microprice::feed {
namespace {

TEST(WireTest, EventRoundTripsThroughWireFormat) {
  const BookEvent event{EventType::Execute, Side::Sell, 42, 77, 10'123, 300, 200, 34'200'000'000'000};
  const auto decoded = from_wire(to_wire(event, 3));
  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(*decoded, event);
}

TEST(WireTest, RejectsUnknownTypeAndSide) {
  WireMessage message = to_wire(BookEvent{}, 1);
  message.type = 'Z';
  EXPECT_FALSE(from_wire(message).has_value());
  message = to_wire(BookEvent{}, 1);
  message.side = 'Q';
  EXPECT_FALSE(from_wire(message).has_value());
}

TEST(WireTest, HeaderMustMatchDatagramLength) {
  std::vector<std::byte> datagram(sizeof(PacketHeader) + 2 * sizeof(WireMessage));
  PacketHeader header;
  header.first_seq = 10;
  header.count = 2;
  write_pod(std::span<std::byte>(datagram), 0, header);
  ASSERT_TRUE(parse_header(datagram).has_value());
  EXPECT_EQ(parse_header(datagram)->first_seq, 10u);
  datagram.pop_back();
  EXPECT_FALSE(parse_header(datagram).has_value());
  EXPECT_FALSE(parse_header(std::span<const std::byte>(datagram.data(), 4)).has_value());
}

TEST(WireTest, PacketsFitInOneEthernetFrame) {
  EXPECT_LE(sizeof(PacketHeader) + kMaxMessagesPerPacket * sizeof(WireMessage), kMaxDatagram);
  EXPECT_GE(kMaxMessagesPerPacket, 20u);
}

}  // namespace
}  // namespace microprice::feed
