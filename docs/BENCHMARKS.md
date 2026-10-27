# Benchmarks

Machine: Apple M1, 8 cores, Darwin 27.0.0.

## Matching engine (`make bench`)

| Benchmark | Result |
| --- | --- |
| Throughput, single thread | 30.0M orders per second |
| Heap allocations per order | 0 |
| Latency per operation | p50 42 ns, p99 167 ns, p99.9 292 ns |

Latency samples include roughly 20 ns of steady-clock overhead per call.

## Multicast feed on loopback (`make bench-feed`)

| Measure | Result |
| --- | --- |
| Book events published | 262,641 in 9,381 datagrams |
| Publish rate | 0.20M events per second |
| Messages captured | 262,641 |
| Sequence gaps | 0 (0 messages lost) |
| One-way latency per packet | p50 138.4 µs, p99 239.5 µs |

