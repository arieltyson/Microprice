#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <span>

#include "microprice/events.hpp"

namespace microprice::feed {

static_assert(std::endian::native == std::endian::little,
              "the wire format is little-endian and encoded with memcpy");

// Every datagram starts with this header, followed by `count` messages whose
// sequence numbers are first_seq, first_seq + 1, ... (as in MoldUDP64).
struct PacketHeader {
  std::uint64_t first_seq = 0;
  std::int64_t send_ns = 0;  // publisher's steady clock, for latency measurement
  std::uint16_t count = 0;
  std::uint16_t session = 0;
  std::uint32_t reserved = 0;
};
static_assert(sizeof(PacketHeader) == 24);

// One fixed-width record per book event. The same 48-byte layout is used in
// capture files, so q can read them with a single `1:` call.
struct WireMessage {
  std::uint8_t type = 0;  // 'A', 'E' or 'X'
  std::uint8_t side = 0;  // 'B' or 'S'
  std::uint16_t symbol = 0;
  std::uint32_t reserved = 0;
  std::int64_t ts = 0;
  std::uint64_t id = 0;
  std::uint64_t aggressor = 0;
  std::int64_t price = 0;
  std::uint32_t qty = 0;
  std::uint32_t remaining = 0;
};
static_assert(sizeof(WireMessage) == 48);

inline constexpr std::size_t kMaxDatagram = 1400;  // stays under a 1500-byte MTU
inline constexpr std::size_t kMaxMessagesPerPacket =
    (kMaxDatagram - sizeof(PacketHeader)) / sizeof(WireMessage);

constexpr WireMessage to_wire(const BookEvent& event, std::uint16_t symbol) noexcept {
  WireMessage m;
  m.type = static_cast<std::uint8_t>(event.type);
  m.side = event.side == Side::Buy ? 'B' : 'S';
  m.symbol = symbol;
  m.ts = event.ts;
  m.id = event.id;
  m.aggressor = event.aggressor;
  m.price = event.price;
  m.qty = static_cast<std::uint32_t>(event.qty);
  m.remaining = static_cast<std::uint32_t>(event.remaining);
  return m;
}

// Validates a record from the network before it is trusted.
inline std::optional<BookEvent> from_wire(const WireMessage& m) noexcept {
  if (m.type != 'A' && m.type != 'E' && m.type != 'X') {
    return std::nullopt;
  }
  if (m.side != 'B' && m.side != 'S') {
    return std::nullopt;
  }
  BookEvent event;
  event.type = static_cast<EventType>(m.type);
  event.side = m.side == 'B' ? Side::Buy : Side::Sell;
  event.id = m.id;
  event.aggressor = m.aggressor;
  event.price = m.price;
  event.qty = m.qty;
  event.remaining = m.remaining;
  event.ts = m.ts;
  return event;
}

template <class T>
void write_pod(std::span<std::byte> out, std::size_t offset, const T& value) noexcept {
  std::memcpy(out.data() + offset, &value, sizeof(T));
}

template <class T>
T read_pod(std::span<const std::byte> in, std::size_t offset) noexcept {
  T value;
  std::memcpy(&value, in.data() + offset, sizeof(T));
  return value;
}

// Parses a datagram. Returns nullopt if it is truncated or its count does not
// match its length.
inline std::optional<PacketHeader> parse_header(std::span<const std::byte> datagram) noexcept {
  if (datagram.size() < sizeof(PacketHeader)) {
    return std::nullopt;
  }
  const auto header = read_pod<PacketHeader>(datagram, 0);
  if (datagram.size() != sizeof(PacketHeader) + header.count * sizeof(WireMessage)) {
    return std::nullopt;
  }
  return header;
}

inline WireMessage message_at(std::span<const std::byte> datagram, std::size_t index) noexcept {
  return read_pod<WireMessage>(datagram, sizeof(PacketHeader) + index * sizeof(WireMessage));
}

}  // namespace microprice::feed
