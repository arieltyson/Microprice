#include "microprice/feed/lobster.hpp"

#include <gtest/gtest.h>

namespace microprice::feed {
namespace {

TEST(LobsterTest, ParsesMessageRow) {
  const auto m = parse_lobster_line("34200.004241176,1,16113575,18,5853300,1");
  ASSERT_TRUE(m.has_value());
  EXPECT_EQ(m->ts, 34'200'004'241'176);
  EXPECT_EQ(m->type, 1);
  EXPECT_EQ(m->id, 16113575u);
  EXPECT_EQ(m->size, 18);
  EXPECT_EQ(m->price, 58'533);  // 585.33 USD in cents
  EXPECT_EQ(m->side, Side::Buy);
  EXPECT_FALSE(parse_lobster_line("not,a,row").has_value());
}

TEST(LobsterTest, AppliesSubmitCancelAndExecution) {
  VectorSink sink;
  OrderBook<VectorSink> book(BookConfig{1, 100'000, 1024}, sink);
  OrderId next = 1'000'000;
  EXPECT_TRUE(apply_lobster(book, {1, 1, 10, 100, 5000, Side::Sell}, next));
  EXPECT_TRUE(apply_lobster(book, {2, 2, 10, 30, 5000, Side::Sell}, next));  // partial cancel
  EXPECT_EQ(book.order_qty(10), 70);
  EXPECT_TRUE(apply_lobster(book, {3, 4, 10, 20, 5000, Side::Sell}, next));  // execution
  EXPECT_EQ(book.order_qty(10), 50);
  EXPECT_EQ(sink.events.back().type, EventType::Execute);
  EXPECT_EQ(sink.events.back().aggressor, 1'000'000u);
  EXPECT_TRUE(apply_lobster(book, {4, 3, 10, 50, 5000, Side::Sell}, next));  // delete
  EXPECT_FALSE(book.contains(10));
  EXPECT_FALSE(apply_lobster(book, {5, 5, 11, 10, 5000, Side::Buy}, next));  // hidden
}

}  // namespace
}  // namespace microprice::feed
