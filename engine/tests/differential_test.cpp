// Drives the engine and a deliberately simple reference book with the same
// random order flow and requires identical event streams. The reference uses
// std::map and std::list, so its correctness can be checked by reading it.

#include <gtest/gtest.h>

#include <algorithm>
#include <functional>
#include <list>
#include <map>
#include <random>
#include <unordered_map>
#include <vector>

#include "microprice/order_book.hpp"

namespace microprice {
namespace {

class ReferenceBook {
 public:
  std::vector<BookEvent> events;

  void submit(const OrderRequest& r) {
    if (r.qty <= 0 || where_.contains(r.id)) {
      return;
    }
    Qty remaining = r.qty;
    if (r.side == Side::Buy) {
      remaining = sweep(asks_, r, remaining, [&](Price p) {
        return r.type == OrderType::Market || p <= r.price;
      });
    } else {
      remaining = sweep(bids_, r, remaining, [&](Price p) {
        return r.type == OrderType::Market || p >= r.price;
      });
    }
    if (remaining > 0 && r.type == OrderType::Limit) {
      auto& level = r.side == Side::Buy ? bids_[r.price] : asks_[r.price];
      level.push_back({r.id, remaining});
      where_[r.id] = {r.side, r.price};
      events.push_back({EventType::Add, r.side, r.id, 0, r.price, remaining, remaining, r.ts});
    }
  }

  void cancel(OrderId id, Timestamp ts) {
    const auto it = where_.find(id);
    if (it == where_.end()) {
      return;
    }
    const auto [side, price] = it->second;
    auto& level = level_for(side, price);
    const auto order = std::find_if(level.begin(), level.end(), [&](auto& o) { return o.id == id; });
    events.push_back({EventType::Cancel, side, id, 0, price, order->qty, 0, ts});
    level.erase(order);
    if (level.empty()) {
      erase_level(side, price);
    }
    where_.erase(it);
  }

  void modify(OrderId id, Price price, Qty qty, Timestamp ts) {
    const auto it = where_.find(id);
    if (it == where_.end() || qty <= 0) {
      return;
    }
    const auto [side, old_price] = it->second;
    auto& level = level_for(side, old_price);
    const auto order = std::find_if(level.begin(), level.end(), [&](auto& o) { return o.id == id; });
    if (price == old_price && qty <= order->qty) {
      if (qty < order->qty) {
        events.push_back({EventType::Cancel, side, id, 0, price, order->qty - qty, qty, ts});
        order->qty = qty;
      }
      return;
    }
    cancel(id, ts);
    submit({id, side, OrderType::Limit, price, qty, ts});
  }

 private:
  struct Resting {
    OrderId id;
    Qty qty;
  };
  using Level = std::list<Resting>;

  template <class Book, class Crosses>
  Qty sweep(Book& book, const OrderRequest& r, Qty remaining, Crosses crosses) {
    const Side resting_side = opposite(r.side);
    while (remaining > 0 && !book.empty() && crosses(book.begin()->first)) {
      auto& [price, level] = *book.begin();
      while (remaining > 0 && !level.empty()) {
        Resting& o = level.front();
        const Qty fill = std::min(remaining, o.qty);
        remaining -= fill;
        o.qty -= fill;
        events.push_back({EventType::Execute, resting_side, o.id, r.id, price, fill, o.qty, r.ts});
        if (o.qty == 0) {
          where_.erase(o.id);
          level.pop_front();
        }
      }
      if (level.empty()) {
        book.erase(book.begin());
      }
    }
    return remaining;
  }

  Level& level_for(Side side, Price price) {
    return side == Side::Buy ? bids_.at(price) : asks_.at(price);
  }
  void erase_level(Side side, Price price) {
    if (side == Side::Buy) {
      bids_.erase(price);
    } else {
      asks_.erase(price);
    }
  }

  std::map<Price, Level, std::greater<>> bids_;
  std::map<Price, Level> asks_;
  std::unordered_map<OrderId, std::pair<Side, Price>> where_;
};

void run_differential(std::uint64_t seed, int steps) {
  VectorSink sink;
  OrderBook<VectorSink> book{BookConfig{1, 2000, 1u << 16}, sink};
  ReferenceBook reference;
  std::mt19937_64 rng(seed);
  std::vector<OrderId> live;
  OrderId next_id = 1;
  const Price mid = 1000;

  for (int step = 0; step < steps; ++step) {
    const Timestamp ts = step;
    const auto roll = rng() % 100;
    if (roll < 55 || live.empty()) {
      const Side side = rng() % 2 == 0 ? Side::Buy : Side::Sell;
      const auto offset = static_cast<Price>(rng() % 20) - 5;
      const Price price = side == Side::Buy ? mid - offset : mid + offset;
      const OrderType type = roll < 50 ? OrderType::Limit : (roll < 53 ? OrderType::Ioc : OrderType::Market);
      const OrderRequest request{next_id, side, type, price, static_cast<Qty>(1 + rng() % 50), ts};
      book.submit(request);
      reference.submit(request);
      if (type == OrderType::Limit) {
        live.push_back(next_id);
      }
      ++next_id;
    } else {
      const std::size_t pick = rng() % live.size();
      const OrderId id = live[pick];
      if (roll < 85) {
        book.cancel(id, ts);
        reference.cancel(id, ts);
        live[pick] = live.back();
        live.pop_back();
      } else {
        const auto price = static_cast<Price>(mid - 10 + static_cast<Price>(rng() % 21));
        const auto qty = static_cast<Qty>(1 + rng() % 50);
        book.modify(id, price, qty, ts);
        reference.modify(id, price, qty, ts);
      }
    }
    ASSERT_EQ(sink.events.size(), reference.events.size()) << "diverged at step " << step;
  }
  ASSERT_EQ(sink.events, reference.events);
}

TEST(DifferentialTest, MatchesReferenceBookOverRandomFlow) {
  for (std::uint64_t seed = 1; seed <= 5; ++seed) {
    run_differential(seed, 200'000);
  }
}

}  // namespace
}  // namespace microprice
