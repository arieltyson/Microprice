#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <span>
#include <vector>

#include "microprice/feed/lobster.hpp"
#include "microprice/order_book.hpp"

namespace microprice {

// Avellaneda-Stoikov market maker run against replayed order flow. This is the
// C++ twin of research/microprice/backtest.py::run_reference; a parity test
// requires both to produce identical fills.
struct MarketMakerParams {
  double gamma = 0.1;
  double kappa = 1.5;
  double tau_s = 30.0;
  std::int64_t quote_lots = 1;
  std::int64_t max_inventory_lots = 10;
  double alpha = 0.0;
  double beta = 0.0;
  double latency_ms = 1.0;
  double min_sigma2 = 0.05;
  std::int64_t lot = 100;
};

struct Fill {
  Timestamp ts = 0;
  int side = 0;  // +1 bought, -1 sold
  Price price = 0;
  Qty qty = 0;
  double mid = 0;  // mid at the last decision before the fill
};

struct MarketMakerResult {
  std::vector<double> equity;
  std::vector<std::int64_t> inventory;
  std::vector<Fill> fills;
  std::int64_t quotes_placed = 0;
  double spread_capture = 0;
  double final_pnl = 0;
};

// Columns of a LOBSTER message file (prices USD x 10000) and per-decision inputs.
struct MarketInputs {
  std::span<const std::int64_t> ts;
  std::span<const std::int32_t> type;
  std::span<const std::uint64_t> id;
  std::span<const std::int64_t> size;
  std::span<const std::int64_t> price;
  std::span<const std::int8_t> direction;
  std::span<const std::int64_t> grid_ns;
  std::span<const double> mid;
  std::span<const double> sigma2;
  std::span<const double> forecast;
  std::span<const double> sentiment;
};

inline constexpr OrderId kStrategyIdBase = OrderId{1} << 61;

namespace detail {

struct StrategyState {
  std::int64_t inventory = 0;
  double cash = 0;
  double spread_capture = 0;
  double reference_mid = 0;
  std::vector<Fill>* fills = nullptr;
};

// Books the strategy's executions the moment the engine reports them.
struct StrategySink {
  StrategyState* state = nullptr;
  void on_event(const BookEvent& event) noexcept {
    if (event.type != EventType::Execute || event.id < kStrategyIdBase) {
      return;
    }
    const int side = event.side == Side::Buy ? 1 : -1;
    state->inventory += side * event.qty;
    state->cash -= static_cast<double>(side * event.qty * event.price);
    state->spread_capture += static_cast<double>(side * event.qty) * (state->reference_mid - static_cast<double>(event.price));
    state->fills->push_back(Fill{event.ts, side, event.price, event.qty, state->reference_mid});
  }
};

struct QuoteState {
  OrderId id = 0;
  Price price = 0;
  bool live = false;
};

}  // namespace detail

inline MarketMakerResult run_market_maker(const MarketInputs& in, const MarketMakerParams& p,
                                          Price max_price_ticks = 200'000) {
  MarketMakerResult result;
  const std::size_t steps = in.grid_ns.size();
  result.equity.assign(steps, 0.0);
  result.inventory.assign(steps, 0);
  detail::StrategyState state;
  state.fills = &result.fills;
  state.reference_mid = steps > 0 ? in.mid[0] : 0.0;
  detail::StrategySink sink{&state};
  OrderBook<detail::StrategySink> book(BookConfig{1, max_price_ticks, 1u << 21}, sink);

  const std::size_t rows = in.ts.size();
  const auto latency_ns = static_cast<std::int64_t>(p.latency_ms * 1e6);
  OrderId next_aggressor = OrderId{1} << 62;
  std::size_t done = 0;
  const auto advance_to = [&](std::int64_t t) {
    while (done < rows && in.ts[done] <= t) {
      const feed::LobsterMessage m{in.ts[done], in.type[done], in.id[done], in.size[done], in.price[done] / 100,
                                   in.direction[done] > 0 ? Side::Buy : Side::Sell};
      feed::apply_lobster(book, m, next_aggressor);
      ++done;
    }
  };

  detail::QuoteState bid_quote, ask_quote;
  OrderId next_id = kStrategyIdBase;
  const Qty size = p.quote_lots * p.lot;
  const double spread_term = (2.0 / p.gamma) * std::log1p(p.gamma / p.kappa);

  for (std::size_t k = 0; k < steps; ++k) {
    advance_to(in.grid_ns[k]);
    const double m = in.mid[k];
    if (!std::isfinite(m)) {
      result.equity[k] = k ? result.equity[k - 1] : 0.0;
      result.inventory[k] = state.inventory;
      continue;
    }
    state.reference_mid = m;
    result.equity[k] = state.cash + static_cast<double>(state.inventory) * m;
    result.inventory[k] = state.inventory;

    const double sigma2 = std::max(in.sigma2[k], p.min_sigma2);
    const double risk = p.gamma * sigma2 * p.tau_s;
    const double reservation = m - (static_cast<double>(state.inventory) / static_cast<double>(p.lot)) * risk +
                               p.alpha * in.forecast[k] + p.beta * in.sentiment[k];
    const double half = 0.5 * (risk + spread_term);

    const std::int64_t at = in.grid_ns[k] + latency_ns;
    advance_to(at);
    auto want_bid = static_cast<Price>(std::floor(reservation - half));
    auto want_ask = static_cast<Price>(std::ceil(reservation + half));
    if (const auto best_ask = book.best_ask()) {
      want_bid = std::min(want_bid, *best_ask - 1);
    }
    if (const auto best_bid = book.best_bid()) {
      want_ask = std::max(want_ask, *best_bid + 1);
    }
    want_bid = std::clamp<Price>(want_bid, 1, max_price_ticks);
    want_ask = std::clamp<Price>(want_ask, 1, max_price_ticks);
    const bool allow_bid = state.inventory + size <= p.max_inventory_lots * p.lot;
    const bool allow_ask = state.inventory - size >= -p.max_inventory_lots * p.lot;

    const auto manage = [&](detail::QuoteState& quote, Side side, Price want, bool allowed) {
      const bool alive = quote.live && book.contains(quote.id);
      if (!allowed) {
        if (alive) {
          book.cancel(quote.id, at);
        }
        quote.live = false;
      } else if (alive && quote.price == want) {
        // Keep the order and its place in the queue.
      } else if (alive) {
        book.modify(quote.id, want, size, at);
        quote.price = want;
        ++result.quotes_placed;
      } else {
        book.submit({next_id, side, OrderType::Limit, want, size, at});
        quote = {next_id++, want, true};
        ++result.quotes_placed;
      }
    };
    manage(bid_quote, Side::Buy, want_bid, allow_bid);
    manage(ask_quote, Side::Sell, want_ask, allow_ask);
  }

  // Flatten at the touch: pay half a tick instead of assuming the mid.
  double last_mid = 0;
  for (std::size_t k = steps; k-- > 0;) {
    if (std::isfinite(in.mid[k])) {
      last_mid = in.mid[k];
      break;
    }
  }
  const double sign = state.inventory > 0 ? 1.0 : (state.inventory < 0 ? -1.0 : 0.0);
  state.cash += static_cast<double>(state.inventory) * (last_mid - 0.5 * sign);
  result.spread_capture = state.spread_capture;
  result.final_pnl = state.cash;
  return result;
}

}  // namespace microprice
