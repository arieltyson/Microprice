#pragma once

#include <cstdint>

namespace microprice {

// Prices are integer ticks of 0.01 USD; quantities are shares.
using Price = std::int64_t;
using Qty = std::int64_t;
using OrderId = std::uint64_t;
// Nanoseconds since midnight in the exchange's time zone.
using Timestamp = std::int64_t;

enum class Side : std::uint8_t { Buy = 0, Sell = 1 };

enum class OrderType : std::uint8_t {
  Limit = 0,   // rests any unfilled quantity
  Market = 1,  // trades through the book, never rests
  Ioc = 2,     // trades up to its limit price, never rests
};

constexpr Side opposite(Side side) noexcept {
  return side == Side::Buy ? Side::Sell : Side::Buy;
}

struct OrderRequest {
  OrderId id = 0;
  Side side = Side::Buy;
  OrderType type = OrderType::Limit;
  Price price = 0;  // ignored for market orders
  Qty qty = 0;
  Timestamp ts = 0;
};

enum class Status : std::uint8_t {
  Ok = 0,
  DuplicateId,
  UnknownId,
  InvalidQty,
  PriceOutOfRange,
  BookFull,
};

}  // namespace microprice
