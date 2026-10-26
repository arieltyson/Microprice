#pragma once

#include <bit>
#include <cstdint>
#include <vector>

#include "microprice/order_pool.hpp"
#include "microprice/types.hpp"

namespace microprice {

// Open-addressing hash map from order id to pool index with linear probing and
// backward-shift deletion. Capacity is fixed at construction, so inserts and
// erases never allocate. std::unordered_map allocates a node per insert.
class IdMap {
 public:
  explicit IdMap(std::uint32_t max_entries)
      : slots_(std::bit_ceil(static_cast<std::uint64_t>(max_entries) * 2 + 2)),
        mask_(slots_.size() - 1) {}

  [[nodiscard]] NodeIndex find(OrderId id) const noexcept {
    for (std::uint64_t i = slot_of(id);; i = (i + 1) & mask_) {
      const Slot& slot = slots_[i];
      if (slot.value == kNil) {
        return kNil;
      }
      if (slot.key == id) {
        return slot.value;
      }
    }
  }

  // Returns false if the id is already present.
  bool insert(OrderId id, NodeIndex value) noexcept {
    for (std::uint64_t i = slot_of(id);; i = (i + 1) & mask_) {
      Slot& slot = slots_[i];
      if (slot.value == kNil) {
        slot = Slot{id, value};
        ++size_;
        return true;
      }
      if (slot.key == id) {
        return false;
      }
    }
  }

  bool erase(OrderId id) noexcept {
    std::uint64_t hole = slot_of(id);
    for (;; hole = (hole + 1) & mask_) {
      if (slots_[hole].value == kNil) {
        return false;
      }
      if (slots_[hole].key == id) {
        break;
      }
    }
    // Shift later members of the probe run back so lookups never stop early.
    for (std::uint64_t next = (hole + 1) & mask_; slots_[next].value != kNil;
         next = (next + 1) & mask_) {
      const std::uint64_t home = slot_of(slots_[next].key);
      const bool movable = ((next - home) & mask_) >= ((next - hole) & mask_);
      if (movable) {
        slots_[hole] = slots_[next];
        hole = next;
      }
    }
    slots_[hole] = Slot{};
    --size_;
    return true;
  }

  [[nodiscard]] std::uint32_t size() const noexcept { return size_; }

 private:
  struct Slot {
    OrderId key = 0;
    NodeIndex value = kNil;
  };

  [[nodiscard]] std::uint64_t slot_of(OrderId id) const noexcept {
    // splitmix64 finalizer: sequential ids spread evenly across slots.
    std::uint64_t x = id + 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return (x ^ (x >> 31)) & mask_;
  }

  std::vector<Slot> slots_;
  std::uint64_t mask_;
  std::uint32_t size_ = 0;
};

}  // namespace microprice
