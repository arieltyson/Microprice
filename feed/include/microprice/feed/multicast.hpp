#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

#include "microprice/events.hpp"
#include "microprice/feed/wire.hpp"

namespace microprice::feed {

struct Endpoint {
  std::string group = "239.255.0.1";
  std::uint16_t port = 30001;
  std::string interface_address = "127.0.0.1";  // local interface for send and join
};

std::int64_t steady_now_ns() noexcept;

// Batches book events into datagrams and sends them to a multicast group.
// Socket setup throws std::system_error; publishing never throws.
class MulticastPublisher {
 public:
  MulticastPublisher(const Endpoint& endpoint, std::uint16_t session, int ttl = 0);
  ~MulticastPublisher();
  MulticastPublisher(const MulticastPublisher&) = delete;
  MulticastPublisher& operator=(const MulticastPublisher&) = delete;

  // Queues one event and sends the datagram once it is full.
  void publish(const BookEvent& event, std::uint16_t symbol) noexcept;
  // Sends any queued messages.
  void flush() noexcept;

  [[nodiscard]] std::uint64_t next_seq() const noexcept { return next_seq_; }
  [[nodiscard]] std::uint64_t packets_sent() const noexcept { return packets_sent_; }
  [[nodiscard]] std::uint64_t send_errors() const noexcept { return send_errors_; }

 private:
  int fd_ = -1;
  std::array<std::byte, kMaxDatagram> buffer_{};
  std::size_t pending_ = 0;
  std::uint64_t next_seq_ = 1;
  std::uint64_t packets_sent_ = 0;
  std::uint64_t send_errors_ = 0;
  std::uint16_t session_;
  std::array<std::byte, 16> destination_{};  // sockaddr_in, kept opaque here
};

struct ReceiverStats {
  std::uint64_t packets = 0;
  std::uint64_t messages = 0;
  std::uint64_t malformed = 0;
  std::uint64_t gaps = 0;           // number of times the sequence jumped
  std::uint64_t lost_messages = 0;  // messages skipped across all gaps
  std::uint64_t duplicates = 0;     // packets entirely at or below the expected sequence
};

// Joins a multicast group, validates datagrams and detects sequence gaps.
class MulticastReceiver {
 public:
  explicit MulticastReceiver(const Endpoint& endpoint, int receive_buffer_bytes = 8 << 20);
  ~MulticastReceiver();
  MulticastReceiver(const MulticastReceiver&) = delete;
  MulticastReceiver& operator=(const MulticastReceiver&) = delete;

  // Waits up to timeout_ms for one datagram, then calls handler(seq, message)
  // for each new message in it. Returns false if nothing arrived.
  template <class Handler>
  bool poll(int timeout_ms, Handler&& handler) {
    std::span<const std::byte> datagram;
    std::int64_t received_ns = 0;
    if (!receive(timeout_ms, datagram, received_ns)) {
      return false;
    }
    const auto header = parse_header(datagram);
    if (!header) {
      ++stats_.malformed;
      return true;
    }
    ++stats_.packets;
    latencies_ns_.push_back(received_ns - header->send_ns);
    const std::uint64_t last = header->first_seq + header->count;  // one past the end
    if (last <= expected_seq_) {
      ++stats_.duplicates;
      return true;
    }
    if (header->first_seq > expected_seq_) {
      ++stats_.gaps;
      stats_.lost_messages += header->first_seq - expected_seq_;
    }
    for (std::uint16_t i = 0; i < header->count; ++i) {
      const std::uint64_t seq = header->first_seq + i;
      if (seq < expected_seq_) {
        continue;  // overlap with data already delivered
      }
      handler(seq, message_at(datagram, i));
      ++stats_.messages;
    }
    expected_seq_ = last;
    return true;
  }

  [[nodiscard]] const ReceiverStats& stats() const noexcept { return stats_; }
  [[nodiscard]] std::uint64_t expected_seq() const noexcept { return expected_seq_; }
  // One-way publish-to-receive latency per packet, in nanoseconds.
  [[nodiscard]] const std::vector<std::int64_t>& latencies_ns() const noexcept { return latencies_ns_; }

 private:
  bool receive(int timeout_ms, std::span<const std::byte>& datagram, std::int64_t& received_ns);

  int fd_ = -1;
  std::array<std::byte, 65536> buffer_{};
  std::uint64_t expected_seq_ = 1;
  ReceiverStats stats_;
  std::vector<std::int64_t> latencies_ns_;
};

}  // namespace microprice::feed
