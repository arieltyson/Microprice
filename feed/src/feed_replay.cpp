// Replays a LOBSTER message file through the matching engine and publishes
// every resulting book event over UDP multicast.
//
//   feed_replay --messages data/synthetic/AAPL_message.csv --symbol 1 [--rate 0]

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <string_view>
#include <thread>

#include "microprice/feed/lobster.hpp"
#include "microprice/feed/multicast.hpp"
#include "microprice/order_book.hpp"

namespace {

struct PublisherSink {
  microprice::feed::MulticastPublisher* publisher = nullptr;
  std::uint16_t symbol = 0;
  std::uint64_t count = 0;
  void on_event(const microprice::BookEvent& event) noexcept {
    publisher->publish(event, symbol);
    ++count;
  }
};

struct Options {
  std::string messages;
  microprice::feed::Endpoint endpoint;
  std::uint16_t symbol = 1;
  double rate = 0;  // events per second; 0 sends as fast as possible
};

Options parse(int argc, char** argv) {
  Options options;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string_view key = argv[i];
    const std::string value = argv[i + 1];
    if (key == "--messages") options.messages = value;
    else if (key == "--group") options.endpoint.group = value;
    else if (key == "--port") options.endpoint.port = static_cast<std::uint16_t>(std::stoi(value));
    else if (key == "--interface") options.endpoint.interface_address = value;
    else if (key == "--symbol") options.symbol = static_cast<std::uint16_t>(std::stoi(value));
    else if (key == "--rate") options.rate = std::stod(value);
  }
  return options;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse(argc, argv);
  microprice::feed::LobsterReader reader(options.messages);
  if (options.messages.empty() || !reader.ok()) {
    std::fprintf(stderr, "usage: feed_replay --messages FILE [--symbol N] [--rate EVENTS_PER_SEC]\n");
    return EXIT_FAILURE;
  }
  microprice::feed::MulticastPublisher publisher(options.endpoint, options.symbol);
  PublisherSink sink{&publisher, options.symbol};
  microprice::OrderBook<PublisherSink> book(microprice::BookConfig{1, 1'000'000, 1u << 22}, sink);

  microprice::OrderId next_aggressor = 1ULL << 62;
  std::uint64_t applied = 0;
  const auto start = std::chrono::steady_clock::now();
  while (const auto message = reader.next()) {
    applied += microprice::feed::apply_lobster(book, *message, next_aggressor) ? 1 : 0;
    if (options.rate > 0) {
      const auto due = start + std::chrono::duration<double>(static_cast<double>(sink.count) / options.rate);
      std::this_thread::sleep_until(due);
    }
  }
  publisher.flush();
  const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  std::printf(
      "{\"messages_applied\": %llu, \"events_published\": %llu, \"packets\": %llu, "
      "\"send_errors\": %llu, \"seconds\": %.3f, \"events_per_sec\": %.0f}\n",
      static_cast<unsigned long long>(applied), static_cast<unsigned long long>(sink.count),
      static_cast<unsigned long long>(publisher.packets_sent()),
      static_cast<unsigned long long>(publisher.send_errors()), seconds,
      static_cast<double>(sink.count) / seconds);
  return EXIT_SUCCESS;
}
