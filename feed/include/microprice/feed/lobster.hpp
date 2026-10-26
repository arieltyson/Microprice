#pragma once

#include <cmath>
#include <cstdint>
#include <fstream>
#include <optional>
#include <sstream>
#include <string>

#include "microprice/order_book.hpp"

namespace microprice::feed {

// One row of a LOBSTER message file:
// time (seconds after midnight), type, order id, size, price (USD x 10000), direction.
struct LobsterMessage {
  Timestamp ts = 0;
  int type = 0;
  OrderId id = 0;
  Qty size = 0;
  Price price = 0;  // converted to 0.01 ticks
  Side side = Side::Buy;
};

inline std::optional<LobsterMessage> parse_lobster_line(const std::string& line) {
  std::istringstream in(line);
  double seconds = 0;
  long long type = 0, id = 0, size = 0, price = 0, direction = 0;
  char comma = 0;
  if (!(in >> seconds >> comma >> type >> comma >> id >> comma >> size >> comma >> price >> comma >>
        direction)) {
    return std::nullopt;
  }
  LobsterMessage m;
  m.ts = static_cast<Timestamp>(std::llround(seconds * 1e9));
  m.type = static_cast<int>(type);
  m.id = static_cast<OrderId>(id);
  m.size = size;
  m.price = price / 100;
  m.side = direction > 0 ? Side::Buy : Side::Sell;
  return m;
}

// Applies one LOBSTER message to a book. Executions become marketable orders
// from the opposite side, so any other resting orders (such as a strategy's
// quotes) compete for the fill by price-time priority. Returns false for
// messages that do not change the visible book.
template <class Book>
bool apply_lobster(Book& book, const LobsterMessage& m, OrderId& next_aggressor_id) {
  switch (m.type) {
    case 1:
      return book.submit({m.id, m.side, OrderType::Limit, m.price, m.size, m.ts}) == Status::Ok;
    case 2: {
      const Qty current = book.order_qty(m.id);
      if (current == 0) {
        return false;
      }
      if (m.size >= current) {
        return book.cancel(m.id, m.ts) == Status::Ok;
      }
      return book.modify(m.id, m.price, current - m.size, m.ts) == Status::Ok;
    }
    case 3:
      return book.cancel(m.id, m.ts) == Status::Ok;
    case 4:
      return book.submit({next_aggressor_id++, opposite(m.side), OrderType::Market, 0, m.size, m.ts}) ==
             Status::Ok;
    default:
      return false;  // 5 hidden execution, 6 cross trade, 7 trading halt
  }
}

class LobsterReader {
 public:
  explicit LobsterReader(const std::string& path) : in_(path) {}
  [[nodiscard]] bool ok() const { return in_.good(); }

  std::optional<LobsterMessage> next() {
    std::string line;
    while (std::getline(in_, line)) {
      if (auto message = parse_lobster_line(line)) {
        return message;
      }
    }
    return std::nullopt;
  }

 private:
  std::ifstream in_;
};

}  // namespace microprice::feed
