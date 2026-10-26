#pragma once

#include <cstdint>
#include <limits>
#include <vector>

#include "microprice/types.hpp"

namespace microprice {

using NodeIndex = std::uint32_t;
inline constexpr NodeIndex kNil = std::numeric_limits<NodeIndex>::max();

struct OrderNode {
  OrderId id = 0;
  Price price = 0;
  Qty qty = 0;
  NodeIndex prev = kNil;
  NodeIndex next = kNil;
  Side side = Side::Buy;
};

// Fixed-capacity node storage. All memory is allocated in the constructor, so
// acquiring and releasing nodes on the hot path never touches the allocator.
class OrderPool {
 public:
  explicit OrderPool(std::uint32_t capacity) : nodes_(capacity), free_(capacity) {
    for (std::uint32_t i = 0; i < capacity; ++i) {
      free_[i] = capacity - 1 - i;
    }
  }

  [[nodiscard]] NodeIndex acquire() noexcept {
    if (free_.empty()) {
      return kNil;
    }
    const NodeIndex index = free_.back();
    free_.pop_back();
    return index;
  }

  void release(NodeIndex index) noexcept {
    nodes_[index] = OrderNode{};
    free_.push_back(index);  // never reallocates: size stays <= capacity
  }

  [[nodiscard]] OrderNode& operator[](NodeIndex index) noexcept { return nodes_[index]; }
  [[nodiscard]] const OrderNode& operator[](NodeIndex index) const noexcept { return nodes_[index]; }

  [[nodiscard]] std::uint32_t capacity() const noexcept {
    return static_cast<std::uint32_t>(nodes_.size());
  }
  [[nodiscard]] std::uint32_t in_use() const noexcept {
    return capacity() - static_cast<std::uint32_t>(free_.size());
  }

 private:
  std::vector<OrderNode> nodes_;
  std::vector<NodeIndex> free_;
};

}  // namespace microprice
