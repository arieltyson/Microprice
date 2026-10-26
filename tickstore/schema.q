/ Microprice tick store schema.
/ Times are nanosecond timestamps in UTC; prices are integer ticks of 0.01 USD.

/ Every book event from the multicast feed (fixed 48-byte capture records).
events:([] time:`timestamp$(); sym:`symbol$(); typ:`char$(); side:`char$(); id:`long$(); aggressor:`long$(); price:`long$(); qty:`long$(); remaining:`long$())

/ Top of book after every LOBSTER message.
quote:([] time:`timestamp$(); sym:`symbol$(); bid:`long$(); ask:`long$(); bsize:`long$(); asize:`long$())

/ Executions; side is the aggressor's side (1 buy, -1 sell).
trade:([] time:`timestamp$(); sym:`symbol$(); price:`long$(); size:`long$(); side:`short$())

/ Symbol locate codes used on the wire, in the order of the synthetic profiles.
syms:`AAPL`MSFT`AMZN`GOOG`NVDA`META`JPM`XOM`JNJ`PG
