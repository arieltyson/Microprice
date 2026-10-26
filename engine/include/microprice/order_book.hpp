#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <span>
#include <vector>

#include "microprice/events.hpp"
#include "microprice/id_map.hpp"
#include "microprice/order_pool.hpp"
#include "microprice/types.hpp"

namespace microprice {

struct LevelView {
  Price price = 0;
  Qty qty = 0;
  std::uint32_t orders = 0;
};

struct BookConfig {
  Price min_price = 1;
  Price max_price = 100'000;  // 1,000.00 USD at 0.01 ticks
  std::uint32_t max_orders = 1u << 20;
};

// Price-time priority limit order book for one symbol.
//
// Price levels live in a flat array indexed by tick offset from min_price, and
// each level is an intrusive FIFO of pool nodes. After construction, no
// operation allocates, throws or locks. The sink is a template parameter so
// event delivery is inlined instead of dispatched through a virtual call.
template <EventSink Sink>
class OrderBook {
 public:
  OrderBook(const BookConfig& config, Sink& sink)
      : min_price_(config.min_price),
        max_price_(config.max_price),
        levels_(static_cast<std::size_t>(config.max_price - config.min_price + 1)),
        pool_(config.max_orders),
        ids_(config.max_orders),
        sink_(sink) {}

  Status submit(const OrderRequest& request) noexcept {
    if (request.qty <= 0) {
      return Status::InvalidQty;
    }
    if (request.type != OrderType::Market && !in_range(request.price)) {
      return Status::PriceOutOfRange;
    }
    if (ids_.find(request.id) != kNil) {
      return Status::DuplicateId;
    }
    const Qty remaining = match(request);
    if (remaining > 0 && request.type == OrderType::Limit) {
      return rest(request, remaining);
    }
    return Status::Ok;
  }

  Status cancel(OrderId id, Timestamp ts) noexcept {
    const NodeIndex index = ids_.find(id);
    if (index == kNil) {
      return Status::UnknownId;
    }
    const OrderNode node = pool_[index];
    remove(index);
    sink_.on_event(BookEvent{EventType::Cancel, node.side, id, 0, node.price, node.qty, 0, ts});
    return Status::Ok;
  }

  // Shrinking an order at the same price keeps its queue position. Any other
  // change re-enters the order at the back of the queue, and the new price
  // may trade immediately.
  Status modify(OrderId id, Price price, Qty qty, Timestamp ts) noexcept {
    const NodeIndex index = ids_.find(id);
    if (index == kNil) {
      return Status::UnknownId;
    }
    if (qty <= 0) {
      return Status::InvalidQty;
    }
    if (!in_range(price)) {
      return Status::PriceOutOfRange;
    }
    OrderNode& node = pool_[index];
    if (price == node.price && qty <= node.qty) {
      if (qty == node.qty) {
        return Status::Ok;
      }
      const Qty reduced = node.qty - qty;
      node.qty = qty;
      levels_[level_of(price)].qty -= reduced;
      sink_.on_event(BookEvent{EventType::Cancel, node.side, id, 0, price, reduced, qty, ts});
      return Status::Ok;
    }
    const Side side = node.side;
    if (const Status status = cancel(id, ts); status != Status::Ok) {
      return status;
    }
    return submit(OrderRequest{id, side, OrderType::Limit, price, qty, ts});
  }

  [[nodiscard]] std::optional<Price> best_bid() const noexcept {
    if (best_bid_ < 0) {
      return std::nullopt;
    }
    return price_of(best_bid_);
  }

  [[nodiscard]] std::optional<Price> best_ask() const noexcept {
    if (best_ask_ >= level_count()) {
      return std::nullopt;
    }
    return price_of(best_ask_);
  }

  [[nodiscard]] Qty qty_at(Price price) const noexcept {
    return in_range(price) ? levels_[level_of(price)].qty : 0;
  }

  // Writes up to out.size() levels from the touch outward and returns how many.
  std::size_t top_levels(Side side, std::span<LevelView> out) const noexcept {
    std::size_t written = 0;
    if (side == Side::Buy) {
      for (std::int64_t i = best_bid_; i >= 0 && written < out.size(); --i) {
        if (levels_[static_cast<std::size_t>(i)].orders > 0) {
          out[written++] = view(i);
        }
      }
    } else {
      for (std::int64_t i = best_ask_; i < level_count() && written < out.size(); ++i) {
        if (levels_[static_cast<std::size_t>(i)].orders > 0) {
          out[written++] = view(i);
        }
      }
    }
    return written;
  }

  [[nodiscard]] bool contains(OrderId id) const noexcept { return ids_.find(id) != kNil; }

  [[nodiscard]] Qty order_qty(OrderId id) const noexcept {
    const NodeIndex index = ids_.find(id);
    return index == kNil ? 0 : pool_[index].qty;
  }

  [[nodiscard]] std::optional<Price> order_price(OrderId id) const noexcept {
    const NodeIndex index = ids_.find(id);
    if (index == kNil) {
      return std::nullopt;
    }
    return pool_[index].price;
  }

  // Quantity resting ahead of an order at its price level (time priority).
  [[nodiscard]] Qty queue_ahead(OrderId id) const noexcept {
    const NodeIndex index = ids_.find(id);
    if (index == kNil) {
      return 0;
    }
    Qty ahead = 0;
    for (NodeIndex i = pool_[index].prev; i != kNil; i = pool_[i].prev) {
      ahead += pool_[i].qty;
    }
    return ahead;
  }

  [[nodiscard]] std::uint32_t order_count() const noexcept { return ids_.size(); }
  [[nodiscard]] Price min_price() const noexcept { return min_price_; }
  [[nodiscard]] Price max_price() const noexcept { return max_price_; }

 private:
  struct Level {
    NodeIndex head = kNil;
    NodeIndex tail = kNil;
    Qty qty = 0;
    std::uint32_t orders = 0;
  };

  [[nodiscard]] bool in_range(Price price) const noexcept {
    return price >= min_price_ && price <= max_price_;
  }
  [[nodiscard]] std::int64_t level_count() const noexcept {
    return static_cast<std::int64_t>(levels_.size());
  }
  [[nodiscard]] std::size_t level_of(Price price) const noexcept {
    return static_cast<std::size_t>(price - min_price_);
  }
  [[nodiscard]] Price price_of(std::int64_t level) const noexcept { return min_price_ + level; }
  [[nodiscard]] LevelView view(std::int64_t level) const noexcept {
    const Level& l = levels_[static_cast<std::size_t>(level)];
    return LevelView{price_of(level), l.qty, l.orders};
  }

  // Trades the request against the opposite side and returns what is left.
  Qty match(const OrderRequest& request) noexcept {
    Qty remaining = request.qty;
    const bool buy = request.side == Side::Buy;
    while (remaining > 0) {
      const std::int64_t touch = buy ? best_ask_ : best_bid_;
      if (touch < 0 || touch >= level_count()) {
        break;
      }
      if (request.type != OrderType::Market) {
        const Price touch_price = price_of(touch);
        if (buy ? touch_price > request.price : touch_price < request.price) {
          break;
        }
      }
      Level& level = levels_[static_cast<std::size_t>(touch)];
      while (remaining > 0 && level.head != kNil) {
        const NodeIndex index = level.head;
        OrderNode& resting = pool_[index];
        const Qty fill = std::min(remaining, resting.qty);
        remaining -= fill;
        resting.qty -= fill;
        level.qty -= fill;
        sink_.on_event(BookEvent{EventType::Execute, resting.side, resting.id, request.id,
                                 resting.price, fill, resting.qty, request.ts});
        if (resting.qty == 0) {
          remove(index);
        }
      }
    }
    return remaining;
  }

  Status rest(const OrderRequest& request, Qty qty) noexcept {
    const NodeIndex index = pool_.acquire();
    if (index == kNil) {
      return Status::BookFull;
    }
    OrderNode& node = pool_[index];
    node = OrderNode{request.id, request.price, qty, kNil, kNil, request.side};
    const std::size_t at = level_of(request.price);
    Level& level = levels_[at];
    node.prev = level.tail;
    if (level.tail != kNil) {
      pool_[level.tail].next = index;
    } else {
      level.head = index;
    }
    level.tail = index;
    level.qty += qty;
    ++level.orders;
    ids_.insert(request.id, index);
    const auto signed_at = static_cast<std::int64_t>(at);
    if (request.side == Side::Buy) {
      best_bid_ = std::max(best_bid_, signed_at);
    } else {
      best_ask_ = std::min(best_ask_, signed_at);
    }
    sink_.on_event(BookEvent{EventType::Add, request.side, request.id, 0, request.price, qty, qty,
                             request.ts});
    return Status::Ok;
  }

  // Unlinks a node, releases it and moves the touch past emptied levels.
  void remove(NodeIndex index) noexcept {
    const OrderNode node = pool_[index];
    const std::size_t at = level_of(node.price);
    Level& level = levels_[at];
    if (node.prev != kNil) {
      pool_[node.prev].next = node.next;
    } else {
      level.head = node.next;
    }
    if (node.next != kNil) {
      pool_[node.next].prev = node.prev;
    } else {
      level.tail = node.prev;
    }
    level.qty -= node.qty;
    --level.orders;
    ids_.erase(node.id);
    pool_.release(index);
    if (level.orders == 0) {
      const auto signed_at = static_cast<std::int64_t>(at);
      if (node.side == Side::Buy && signed_at == best_bid_) {
        while (best_bid_ >= 0 && levels_[static_cast<std::size_t>(best_bid_)].orders == 0) {
          --best_bid_;
        }
      } else if (node.side == Side::Sell && signed_at == best_ask_) {
        while (best_ask_ < level_count() &&
               levels_[static_cast<std::size_t>(best_ask_)].orders == 0) {
          ++best_ask_;
        }
      }
    }
  }

  Price min_price_;
  Price max_price_;
  std::vector<Level> levels_;
  OrderPool pool_;
  IdMap ids_;
  Sink& sink_;
  std::int64_t best_bid_ = -1;
  std::int64_t best_ask_ = std::numeric_limits<std::int64_t>::max();
};

}  // namespace microprice
