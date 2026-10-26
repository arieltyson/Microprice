// Python bindings for the matching engine. Single-call methods serve the
// strategy loop; the batch methods replay whole arrays of LOBSTER messages in
// C++ so historical order flow does not cross the Python boundary per message.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <optional>
#include <vector>

#include "microprice/feed/lobster.hpp"
#include "microprice/order_book.hpp"

namespace py = pybind11;
using namespace microprice;

namespace {

class Engine {
 public:
  Engine(Price min_price, Price max_price, std::uint32_t max_orders)
      : book_(BookConfig{min_price, max_price, max_orders}, sink_) {}

  int submit(OrderId id, int side, int type, Price price, Qty qty, Timestamp ts) {
    return static_cast<int>(book_.submit(
        {id, static_cast<Side>(side), static_cast<OrderType>(type), price, qty, ts}));
  }
  int cancel(OrderId id, Timestamp ts) { return static_cast<int>(book_.cancel(id, ts)); }
  int modify(OrderId id, Price price, Qty qty, Timestamp ts) {
    return static_cast<int>(book_.modify(id, price, qty, ts));
  }

  std::optional<Price> best_bid() const { return book_.best_bid(); }
  std::optional<Price> best_ask() const { return book_.best_ask(); }
  Qty qty_at(Price price) const { return book_.qty_at(price); }
  Qty order_qty(OrderId id) const { return book_.order_qty(id); }
  Qty queue_ahead(OrderId id) const { return book_.queue_ahead(id); }
  bool contains(OrderId id) const { return book_.contains(id); }
  std::uint32_t order_count() const { return book_.order_count(); }

  // Returns (prices, sizes) for the top n levels of one side.
  py::tuple top_levels(int side, std::size_t n) const {
    std::vector<LevelView> levels(n);
    const std::size_t count = book_.top_levels(static_cast<Side>(side), levels);
    py::array_t<std::int64_t> prices(static_cast<py::ssize_t>(n));
    py::array_t<std::int64_t> sizes(static_cast<py::ssize_t>(n));
    auto p = prices.mutable_unchecked<1>();
    auto s = sizes.mutable_unchecked<1>();
    for (std::size_t i = 0; i < n; ++i) {
      const auto at = static_cast<py::ssize_t>(i);
      p(at) = i < count ? levels[i].price : 0;
      s(at) = i < count ? levels[i].qty : 0;
    }
    return py::make_tuple(prices, sizes);
  }

  // Replays messages [start, end) of LOBSTER columns. Prices are USD x 10000.
  std::size_t apply_lobster(py::array_t<std::int64_t> ts, py::array_t<std::int32_t> type,
                            py::array_t<std::uint64_t> id, py::array_t<std::int64_t> size,
                            py::array_t<std::int64_t> price, py::array_t<std::int8_t> direction,
                            std::size_t start, std::size_t end) {
    auto t = ts.unchecked<1>();
    auto k = type.unchecked<1>();
    auto i = id.unchecked<1>();
    auto q = size.unchecked<1>();
    auto p = price.unchecked<1>();
    auto d = direction.unchecked<1>();
    std::size_t applied = 0;
    for (std::size_t row = start; row < end; ++row) {
      const auto r = static_cast<py::ssize_t>(row);
      const feed::LobsterMessage m{t(r), k(r), i(r), q(r), p(r) / 100, d(r) > 0 ? Side::Buy : Side::Sell};
      applied += feed::apply_lobster(book_, m, next_aggressor_) ? 1 : 0;
    }
    return applied;
  }

  // Returns and clears every event since the last drain, as numpy columns.
  py::dict drain_events() {
    const auto n = static_cast<py::ssize_t>(sink_.events.size());
    py::array_t<std::uint8_t> type(n), side(n);
    py::array_t<std::uint64_t> id(n), aggressor(n);
    py::array_t<std::int64_t> price(n), qty(n), remaining(n), ts(n);
    auto a = type.mutable_unchecked<1>();
    auto b = side.mutable_unchecked<1>();
    auto c = id.mutable_unchecked<1>();
    auto e = aggressor.mutable_unchecked<1>();
    auto f = price.mutable_unchecked<1>();
    auto g = qty.mutable_unchecked<1>();
    auto h = remaining.mutable_unchecked<1>();
    auto j = ts.mutable_unchecked<1>();
    for (py::ssize_t r = 0; r < n; ++r) {
      const BookEvent& event = sink_.events[static_cast<std::size_t>(r)];
      a(r) = static_cast<std::uint8_t>(event.type);
      b(r) = static_cast<std::uint8_t>(event.side);
      c(r) = event.id;
      e(r) = event.aggressor;
      f(r) = event.price;
      g(r) = event.qty;
      h(r) = event.remaining;
      j(r) = event.ts;
    }
    sink_.events.clear();
    py::dict out;
    out["type"] = type;
    out["side"] = side;
    out["id"] = id;
    out["aggressor"] = aggressor;
    out["price"] = price;
    out["qty"] = qty;
    out["remaining"] = remaining;
    out["ts"] = ts;
    return out;
  }

  std::size_t pending_events() const { return sink_.events.size(); }

 private:
  VectorSink sink_;
  OrderBook<VectorSink> book_;
  OrderId next_aggressor_ = 1ULL << 62;
};

}  // namespace

PYBIND11_MODULE(_engine, m) {
  m.doc() = "Price-time priority matching engine (C++20)";
  m.attr("BUY") = 0;
  m.attr("SELL") = 1;
  m.attr("LIMIT") = 0;
  m.attr("MARKET") = 1;
  m.attr("IOC") = 2;
  m.attr("ADD") = static_cast<int>('A');
  m.attr("EXECUTE") = static_cast<int>('E');
  m.attr("CANCEL") = static_cast<int>('X');

  py::class_<Engine>(m, "Engine")
      .def(py::init<Price, Price, std::uint32_t>(), py::arg("min_price") = 1,
           py::arg("max_price") = 1'000'000, py::arg("max_orders") = 1u << 22)
      .def("submit", &Engine::submit, py::arg("id"), py::arg("side"), py::arg("type"), py::arg("price"),
           py::arg("qty"), py::arg("ts"))
      .def("cancel", &Engine::cancel, py::arg("id"), py::arg("ts"))
      .def("modify", &Engine::modify, py::arg("id"), py::arg("price"), py::arg("qty"), py::arg("ts"))
      .def("best_bid", &Engine::best_bid)
      .def("best_ask", &Engine::best_ask)
      .def("qty_at", &Engine::qty_at)
      .def("order_qty", &Engine::order_qty)
      .def("queue_ahead", &Engine::queue_ahead)
      .def("contains", &Engine::contains)
      .def("order_count", &Engine::order_count)
      .def("top_levels", &Engine::top_levels, py::arg("side"), py::arg("n"))
      .def("apply_lobster", &Engine::apply_lobster)
      .def("drain_events", &Engine::drain_events)
      .def("pending_events", &Engine::pending_events);
}
