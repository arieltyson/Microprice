#pragma once

#include <vector>

#include "microprice/types.hpp"

namespace microprice {

// Every change to the book is reported as one of three events, matching the
// Add, Execute and Cancel messages of an ITCH-style feed.
enum class EventType : std::uint8_t {
  Add = 'A',      // order rests on the book
  Execute = 'E',  // resting order traded against an aggressor
  Cancel = 'X',   // resting order reduced; remaining == 0 means removed
};

struct BookEvent {
  EventType type = EventType::Add;
  Side side = Side::Buy;  // side of the resting order
  OrderId id = 0;         // resting order
  OrderId aggressor = 0;  // Execute only
  Price price = 0;
  Qty qty = 0;        // added, executed or cancelled quantity
  Qty remaining = 0;  // resting quantity after the event
  Timestamp ts = 0;

  friend bool operator==(const BookEvent&, const BookEvent&) = default;
};

template <class S>
concept EventSink = requires(S sink, const BookEvent& event) {
  { sink.on_event(event) };
};

struct NullSink {
  void on_event(const BookEvent&) noexcept {}
};

struct CountingSink {
  std::uint64_t count = 0;
  void on_event(const BookEvent&) noexcept { ++count; }
};

struct VectorSink {
  std::vector<BookEvent> events;
  void on_event(const BookEvent& event) { events.push_back(event); }
};

}  // namespace microprice
