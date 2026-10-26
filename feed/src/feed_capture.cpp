// Joins the multicast feed, detects gaps and writes every message to a
// capture file of fixed 48-byte records for the kdb+ loader.
//
// The network thread only decodes and pushes into a lock-free ring; a second
// thread does the file I/O, so a slow disk never delays reading the socket.
//
//   feed_capture --out data/capture/AAPL.bin [--idle-ms 2000]

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "microprice/feed/multicast.hpp"
#include "microprice/feed/spsc_ring.hpp"

namespace {

struct Options {
  std::string out;
  microprice::feed::Endpoint endpoint;
  int idle_ms = 2000;
};

Options parse(int argc, char** argv) {
  Options options;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string_view key = argv[i];
    const std::string value = argv[i + 1];
    if (key == "--out") options.out = value;
    else if (key == "--group") options.endpoint.group = value;
    else if (key == "--port") options.endpoint.port = static_cast<std::uint16_t>(std::stoi(value));
    else if (key == "--interface") options.endpoint.interface_address = value;
    else if (key == "--idle-ms") options.idle_ms = std::stoi(value);
  }
  return options;
}

double percentile(std::vector<std::int64_t> values, double q) {
  if (values.empty()) {
    return 0;
  }
  std::sort(values.begin(), values.end());
  return static_cast<double>(values[static_cast<std::size_t>(q * static_cast<double>(values.size() - 1))]);
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse(argc, argv);
  if (options.out.empty()) {
    std::fprintf(stderr, "usage: feed_capture --out FILE [--idle-ms MS]\n");
    return EXIT_FAILURE;
  }
  std::ofstream file(options.out, std::ios::binary);
  if (!file) {
    std::fprintf(stderr, "cannot open %s\n", options.out.c_str());
    return EXIT_FAILURE;
  }

  microprice::feed::MulticastReceiver receiver(options.endpoint);
  auto ring = std::make_unique<microprice::feed::SpscRing<microprice::feed::WireMessage, 1u << 16>>();
  std::atomic<bool> done{false};
  std::uint64_t ring_full_spins = 0;

  std::thread writer([&] {
    while (true) {
      if (auto message = ring->try_pop()) {
        file.write(reinterpret_cast<const char*>(&*message), sizeof(microprice::feed::WireMessage));
      } else if (done.load(std::memory_order_acquire)) {
        if (ring->size_approx() == 0) {
          break;
        }
      } else {
        std::this_thread::yield();
      }
    }
  });

  int timeout_ms = 60'000;  // wait for the publisher to start, then stop when it goes quiet
  while (receiver.poll(timeout_ms, [&](std::uint64_t, const auto& message) {
    while (!ring->try_push(message)) {
      ++ring_full_spins;
    }
  })) {
    timeout_ms = options.idle_ms;
  }
  done.store(true, std::memory_order_release);
  writer.join();

  const auto& stats = receiver.stats();
  std::printf(
      "{\"packets\": %llu, \"messages\": %llu, \"gaps\": %llu, \"lost_messages\": %llu, "
      "\"malformed\": %llu, \"ring_full_spins\": %llu, \"latency_p50_ns\": %.0f, "
      "\"latency_p99_ns\": %.0f}\n",
      static_cast<unsigned long long>(stats.packets), static_cast<unsigned long long>(stats.messages),
      static_cast<unsigned long long>(stats.gaps), static_cast<unsigned long long>(stats.lost_messages),
      static_cast<unsigned long long>(stats.malformed), static_cast<unsigned long long>(ring_full_spins),
      percentile(receiver.latencies_ns(), 0.50), percentile(receiver.latencies_ns(), 0.99));
  return stats.gaps == 0 ? EXIT_SUCCESS : 2;
}
