#include <benchmark/benchmark.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <new>
#include <random>
#include <vector>

#include "microprice/order_book.hpp"

// Counts heap allocations so the benchmark can prove the hot path makes none.
namespace {
std::atomic<std::uint64_t> g_allocations{0};
}  // namespace

void* operator new(std::size_t size) {
  g_allocations.fetch_add(1, std::memory_order_relaxed);
  if (void* p = std::malloc(size)) {
    return p;
  }
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

namespace microprice {
namespace {

enum class Op : std::uint8_t { Add, Cancel, Market };

struct Action {
  Op op;
  OrderRequest request;
};

// A realistic mix: most traffic is passive adds and cancels near the touch,
// with occasional marketable orders that walk one or two levels.
std::vector<Action> make_workload(std::size_t count, std::uint64_t seed) {
  std::mt19937_64 rng(seed);
  std::vector<Action> actions;
  actions.reserve(count);
  std::vector<OrderId> live;
  OrderId next = 1;
  const Price mid = 50'000;
  for (std::size_t i = 0; i < count; ++i) {
    const auto roll = rng() % 100;
    const Side side = rng() % 2 == 0 ? Side::Buy : Side::Sell;
    const auto ts = static_cast<Timestamp>(i);
    if (roll < 50 || live.size() < 1000) {
      const auto offset = static_cast<Price>(1 + rng() % 20);
      const Price price = side == Side::Buy ? mid - offset : mid + offset;
      actions.push_back({Op::Add, {next, side, OrderType::Limit, price, static_cast<Qty>(1 + rng() % 100), ts}});
      live.push_back(next++);
    } else if (roll < 95) {
      const std::size_t pick = rng() % live.size();
      actions.push_back({Op::Cancel, {live[pick], side, OrderType::Limit, 0, 0, ts}});
      live[pick] = live.back();
      live.pop_back();
    } else {
      actions.push_back({Op::Market, {next++, side, OrderType::Market, 0, static_cast<Qty>(1 + rng() % 200), ts}});
    }
  }
  return actions;
}

template <class Book>
void apply(Book& book, const Action& action) {
  if (action.op == Op::Cancel) {
    benchmark::DoNotOptimize(book.cancel(action.request.id, action.request.ts));
  } else {
    benchmark::DoNotOptimize(book.submit(action.request));
  }
}

void BM_OrderBookThroughput(benchmark::State& state) {
  const auto actions = make_workload(1'000'000, 42);
  std::uint64_t processed = 0;
  std::uint64_t allocations = 0;
  for (auto _ : state) {
    state.PauseTiming();
    CountingSink sink;
    OrderBook<CountingSink> book{BookConfig{1, 100'000, 1u << 20}, sink};
    const auto before = g_allocations.load(std::memory_order_relaxed);
    state.ResumeTiming();
    for (const Action& action : actions) {
      apply(book, action);
    }
    state.PauseTiming();
    allocations += g_allocations.load(std::memory_order_relaxed) - before;
    processed += actions.size();
    benchmark::DoNotOptimize(sink.count);
    state.ResumeTiming();
  }
  state.counters["orders_per_sec"] = benchmark::Counter(static_cast<double>(processed), benchmark::Counter::kIsRate);
  state.counters["allocs_per_order"] = static_cast<double>(allocations) / static_cast<double>(processed);
}
BENCHMARK(BM_OrderBookThroughput)->Unit(benchmark::kMillisecond)->UseRealTime();

// Per-operation latency percentiles. Each sample times one call with the
// steady clock, so the figures include roughly 20 ns of clock overhead.
void BM_OrderBookLatency(benchmark::State& state) {
  const auto actions = make_workload(1'000'000, 43);
  std::vector<std::int64_t> samples;
  samples.reserve(actions.size());
  for (auto _ : state) {
    samples.clear();
    CountingSink sink;
    OrderBook<CountingSink> book{BookConfig{1, 100'000, 1u << 20}, sink};
    for (const Action& action : actions) {
      const auto start = std::chrono::steady_clock::now();
      apply(book, action);
      const auto end = std::chrono::steady_clock::now();
      samples.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
    }
  }
  std::sort(samples.begin(), samples.end());
  const auto at = [&](double q) {
    return static_cast<double>(samples[static_cast<std::size_t>(q * static_cast<double>(samples.size() - 1))]);
  };
  state.counters["p50_ns"] = at(0.50);
  state.counters["p99_ns"] = at(0.99);
  state.counters["p999_ns"] = at(0.999);
}
BENCHMARK(BM_OrderBookLatency)->Unit(benchmark::kMillisecond)->Iterations(1);

}  // namespace
}  // namespace microprice

BENCHMARK_MAIN();
