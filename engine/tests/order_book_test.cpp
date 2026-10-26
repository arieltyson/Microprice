#include "microprice/order_book.hpp"

#include <gtest/gtest.h>

#include <array>

namespace microprice {
namespace {

class OrderBookTest : public ::testing::Test {
 protected:
  VectorSink sink;
  OrderBook<VectorSink> book{BookConfig{1, 1000, 1024}, sink};

  Status limit(OrderId id, Side side, Price price, Qty qty) {
    return book.submit({id, side, OrderType::Limit, price, qty, static_cast<Timestamp>(id)});
  }
};

TEST_F(OrderBookTest, RestingOrdersSetTheTouch) {
  EXPECT_EQ(limit(1, Side::Buy, 100, 10), Status::Ok);
  EXPECT_EQ(limit(2, Side::Sell, 102, 5), Status::Ok);
  EXPECT_EQ(book.best_bid(), 100);
  EXPECT_EQ(book.best_ask(), 102);
  ASSERT_EQ(sink.events.size(), 2u);
  EXPECT_EQ(sink.events[0].type, EventType::Add);
  EXPECT_EQ(sink.events[1].remaining, 5);
}

TEST_F(OrderBookTest, AggressorTradesInPriceThenTimePriority) {
  limit(1, Side::Sell, 101, 5);
  limit(2, Side::Sell, 100, 5);
  limit(3, Side::Sell, 100, 5);
  sink.events.clear();

  EXPECT_EQ(limit(4, Side::Buy, 101, 12), Status::Ok);
  ASSERT_EQ(sink.events.size(), 3u);
  EXPECT_EQ(sink.events[0].id, 2u);  // best price, first in time
  EXPECT_EQ(sink.events[1].id, 3u);
  EXPECT_EQ(sink.events[2].id, 1u);
  EXPECT_EQ(sink.events[2].qty, 2);
  EXPECT_EQ(sink.events[2].remaining, 3);
  EXPECT_EQ(sink.events[2].aggressor, 4u);
  EXPECT_EQ(book.best_ask(), 101);
  EXPECT_FALSE(book.contains(4));  // fully filled, nothing rests
}

TEST_F(OrderBookTest, LimitRemainderRestsAfterSweeping) {
  limit(1, Side::Sell, 100, 5);
  limit(2, Side::Buy, 101, 8);
  EXPECT_EQ(book.best_bid(), 101);
  EXPECT_EQ(book.order_qty(2), 3);
  EXPECT_FALSE(book.best_ask().has_value());
}

TEST_F(OrderBookTest, MarketAndIocOrdersNeverRest) {
  limit(1, Side::Sell, 100, 5);
  EXPECT_EQ(book.submit({2, Side::Buy, OrderType::Market, 0, 8, 2}), Status::Ok);
  EXPECT_FALSE(book.contains(2));
  limit(3, Side::Sell, 105, 5);
  EXPECT_EQ(book.submit({4, Side::Buy, OrderType::Ioc, 104, 5, 4}), Status::Ok);
  EXPECT_FALSE(book.contains(4));
  EXPECT_EQ(book.order_qty(3), 5);
}

TEST_F(OrderBookTest, CancelRemovesOrderAndMovesTouch) {
  limit(1, Side::Buy, 100, 5);
  limit(2, Side::Buy, 99, 5);
  EXPECT_EQ(book.cancel(1, 3), Status::Ok);
  EXPECT_EQ(book.best_bid(), 99);
  EXPECT_EQ(sink.events.back().type, EventType::Cancel);
  EXPECT_EQ(sink.events.back().remaining, 0);
  EXPECT_EQ(book.cancel(1, 4), Status::UnknownId);
}

TEST_F(OrderBookTest, ShrinkingKeepsQueuePositionAndGrowingLosesIt) {
  limit(1, Side::Buy, 100, 5);
  limit(2, Side::Buy, 100, 5);
  EXPECT_EQ(book.modify(1, 100, 3, 3), Status::Ok);
  EXPECT_EQ(book.queue_ahead(2), 3);
  EXPECT_EQ(book.modify(1, 100, 9, 4), Status::Ok);
  EXPECT_EQ(book.queue_ahead(1), 5);  // now behind order 2
  EXPECT_EQ(book.qty_at(100), 14);
}

TEST_F(OrderBookTest, ModifyToCrossingPriceTrades) {
  limit(1, Side::Sell, 101, 5);
  limit(2, Side::Buy, 99, 5);
  sink.events.clear();
  EXPECT_EQ(book.modify(2, 101, 5, 3), Status::Ok);
  ASSERT_EQ(sink.events.size(), 2u);
  EXPECT_EQ(sink.events[0].type, EventType::Cancel);
  EXPECT_EQ(sink.events[1].type, EventType::Execute);
  EXPECT_FALSE(book.contains(2));
}

TEST_F(OrderBookTest, RejectsInvalidRequests) {
  EXPECT_EQ(limit(1, Side::Buy, 100, 0), Status::InvalidQty);
  EXPECT_EQ(limit(1, Side::Buy, 5000, 1), Status::PriceOutOfRange);
  EXPECT_EQ(limit(1, Side::Buy, 100, 1), Status::Ok);
  EXPECT_EQ(limit(1, Side::Buy, 100, 1), Status::DuplicateId);
}

TEST_F(OrderBookTest, ReportsBookFullWithoutAllocating) {
  VectorSink small_sink;
  OrderBook<VectorSink> small{BookConfig{1, 10, 2}, small_sink};
  EXPECT_EQ(small.submit({1, Side::Buy, OrderType::Limit, 5, 1, 0}), Status::Ok);
  EXPECT_EQ(small.submit({2, Side::Buy, OrderType::Limit, 5, 1, 0}), Status::Ok);
  EXPECT_EQ(small.submit({3, Side::Buy, OrderType::Limit, 5, 1, 0}), Status::BookFull);
}

TEST_F(OrderBookTest, ReportsRestingOrderPrice) {
  limit(1, Side::Sell, 105, 5);
  EXPECT_EQ(book.order_price(1), 105);
  EXPECT_FALSE(book.order_price(2).has_value());
}

TEST_F(OrderBookTest, TopLevelsWalkOutwardFromTheTouch) {
  limit(1, Side::Buy, 100, 5);
  limit(2, Side::Buy, 98, 7);
  limit(3, Side::Buy, 100, 1);
  std::array<LevelView, 3> levels{};
  ASSERT_EQ(book.top_levels(Side::Buy, levels), 2u);
  EXPECT_EQ(levels[0].price, 100);
  EXPECT_EQ(levels[0].qty, 6);
  EXPECT_EQ(levels[0].orders, 2u);
  EXPECT_EQ(levels[1].price, 98);
}

}  // namespace
}  // namespace microprice
