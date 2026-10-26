#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <new>
#include <optional>

namespace microprice::feed {

inline constexpr std::size_t kCacheLine = 64;

// Lock-free single-producer single-consumer ring buffer.
//
// The producer owns `head_`, the consumer owns `tail_`, and each keeps a cached
// copy of the other's index so most operations touch only its own cache line.
// The indices sit on separate cache lines to avoid false sharing.
template <class T, std::size_t Capacity>
class SpscRing {
  static_assert(Capacity >= 2 && (Capacity & (Capacity - 1)) == 0, "capacity must be a power of two");

 public:
  bool try_push(const T& value) noexcept {
    const std::size_t head = head_.load(std::memory_order_relaxed);
    if (head - tail_cache_ == Capacity) {
      tail_cache_ = tail_.load(std::memory_order_acquire);
      if (head - tail_cache_ == Capacity) {
        return false;
      }
    }
    slots_[head & kMask] = value;
    head_.store(head + 1, std::memory_order_release);
    return true;
  }

  std::optional<T> try_pop() noexcept {
    const std::size_t tail = tail_.load(std::memory_order_relaxed);
    if (tail == head_cache_) {
      head_cache_ = head_.load(std::memory_order_acquire);
      if (tail == head_cache_) {
        return std::nullopt;
      }
    }
    T value = slots_[tail & kMask];
    tail_.store(tail + 1, std::memory_order_release);
    return value;
  }

  [[nodiscard]] std::size_t size_approx() const noexcept {
    return head_.load(std::memory_order_acquire) - tail_.load(std::memory_order_acquire);
  }

 private:
  static constexpr std::size_t kMask = Capacity - 1;

  alignas(kCacheLine) std::atomic<std::size_t> head_{0};
  alignas(kCacheLine) std::size_t tail_cache_ = 0;  // producer's view of tail_
  alignas(kCacheLine) std::atomic<std::size_t> tail_{0};
  alignas(kCacheLine) std::size_t head_cache_ = 0;  // consumer's view of head_
  alignas(kCacheLine) std::array<T, Capacity> slots_{};
};

}  // namespace microprice::feed
