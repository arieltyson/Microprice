#include "microprice/feed/multicast.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstring>
#include <system_error>

namespace microprice::feed {
namespace {

[[noreturn]] void fail(const char* what) {
  throw std::system_error(errno, std::generic_category(), what);
}

in_addr parse_address(const std::string& text) {
  in_addr address{};
  if (inet_pton(AF_INET, text.c_str(), &address) != 1) {
    throw std::system_error(EINVAL, std::generic_category(), "invalid IPv4 address: " + text);
  }
  return address;
}

}  // namespace

std::int64_t steady_now_ns() noexcept {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

MulticastPublisher::MulticastPublisher(const Endpoint& endpoint, std::uint16_t session, int ttl)
    : session_(session) {
  fd_ = ::socket(AF_INET, SOCK_DGRAM, 0);
  if (fd_ < 0) {
    fail("socket");
  }
  const auto ttl_byte = static_cast<unsigned char>(ttl);
  const unsigned char loop = 1;
  const in_addr interface_address = parse_address(endpoint.interface_address);
  if (::setsockopt(fd_, IPPROTO_IP, IP_MULTICAST_TTL, &ttl_byte, sizeof ttl_byte) != 0 ||
      ::setsockopt(fd_, IPPROTO_IP, IP_MULTICAST_LOOP, &loop, sizeof loop) != 0 ||
      ::setsockopt(fd_, IPPROTO_IP, IP_MULTICAST_IF, &interface_address, sizeof interface_address) != 0) {
    const int saved = errno;
    ::close(fd_);
    errno = saved;
    fail("setsockopt multicast");
  }
  sockaddr_in destination{};
  destination.sin_family = AF_INET;
  destination.sin_port = htons(endpoint.port);
  destination.sin_addr = parse_address(endpoint.group);
  static_assert(sizeof(destination) <= sizeof(destination_));
  std::memcpy(destination_.data(), &destination, sizeof destination);
}

MulticastPublisher::~MulticastPublisher() {
  flush();
  if (fd_ >= 0) {
    ::close(fd_);
  }
}

void MulticastPublisher::publish(const BookEvent& event, std::uint16_t symbol) noexcept {
  write_pod(buffer_, sizeof(PacketHeader) + pending_ * sizeof(WireMessage), to_wire(event, symbol));
  if (++pending_ == kMaxMessagesPerPacket) {
    flush();
  }
}

void MulticastPublisher::flush() noexcept {
  if (pending_ == 0) {
    return;
  }
  PacketHeader header;
  header.first_seq = next_seq_;
  header.count = static_cast<std::uint16_t>(pending_);
  header.session = session_;
  header.send_ns = steady_now_ns();
  write_pod(buffer_, 0, header);
  const std::size_t length = sizeof(PacketHeader) + pending_ * sizeof(WireMessage);
  const auto sent = ::sendto(fd_, buffer_.data(), length, 0,
                             reinterpret_cast<const sockaddr*>(destination_.data()), sizeof(sockaddr_in));
  if (sent == static_cast<ssize_t>(length)) {
    ++packets_sent_;
  } else {
    ++send_errors_;
  }
  // Sequence numbers advance even if the send fails, so receivers see the gap.
  next_seq_ += pending_;
  pending_ = 0;
}

MulticastReceiver::MulticastReceiver(const Endpoint& endpoint, int receive_buffer_bytes) {
  latencies_ns_.reserve(1 << 20);
  fd_ = ::socket(AF_INET, SOCK_DGRAM, 0);
  if (fd_ < 0) {
    fail("socket");
  }
  const int on = 1;
  ::setsockopt(fd_, SOL_SOCKET, SO_REUSEADDR, &on, sizeof on);
#ifdef SO_REUSEPORT
  ::setsockopt(fd_, SOL_SOCKET, SO_REUSEPORT, &on, sizeof on);
#endif
  // Bursts overflow the default buffer and show up as sequence gaps.
  ::setsockopt(fd_, SOL_SOCKET, SO_RCVBUF, &receive_buffer_bytes, sizeof receive_buffer_bytes);

  sockaddr_in local{};
  local.sin_family = AF_INET;
  local.sin_port = htons(endpoint.port);
  local.sin_addr.s_addr = htonl(INADDR_ANY);
  if (::bind(fd_, reinterpret_cast<const sockaddr*>(&local), sizeof local) != 0) {
    const int saved = errno;
    ::close(fd_);
    errno = saved;
    fail("bind");
  }
  ip_mreq membership{};
  membership.imr_multiaddr = parse_address(endpoint.group);
  membership.imr_interface = parse_address(endpoint.interface_address);
  if (::setsockopt(fd_, IPPROTO_IP, IP_ADD_MEMBERSHIP, &membership, sizeof membership) != 0) {
    const int saved = errno;
    ::close(fd_);
    errno = saved;
    fail("IP_ADD_MEMBERSHIP");
  }
}

MulticastReceiver::~MulticastReceiver() {
  if (fd_ >= 0) {
    ::close(fd_);
  }
}

bool MulticastReceiver::receive(int timeout_ms, std::span<const std::byte>& datagram,
                                std::int64_t& received_ns) {
  pollfd descriptor{fd_, POLLIN, 0};
  if (::poll(&descriptor, 1, timeout_ms) <= 0) {
    return false;
  }
  const auto length = ::recv(fd_, buffer_.data(), buffer_.size(), 0);
  received_ns = steady_now_ns();
  if (length <= 0) {
    return false;
  }
  datagram = std::span<const std::byte>(buffer_.data(), static_cast<std::size_t>(length));
  return true;
}

}  // namespace microprice::feed
