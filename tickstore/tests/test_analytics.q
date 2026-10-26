/ Unit tests for tickstore/analytics.q. Run: q tickstore/tests/test_analytics.q
\l tickstore/schema.q
\l tickstore/analytics.q

failures:0
check:{[name;ok] if[not ok; -1 "FAIL ",name; failures+:1]}

d:2026.10.19
q0:([] time:(`timestamp$d)+09:30:00.000000000+`timespan$1000000000*1 2 3;
      sym:3#`AAPL; bid:100 100 101; ask:101 102 102; bsize:300 200 100; asize:100 100 400)

m:withMicro q0
check["mid";m[`mid]~100.5 101 101.5]
check["spread";m[`spread]~1 2 1]
check["micro weights the far side by the near size";m[`micro;0]=((100*100)+101*300)%400]
check["imbalance";m[`imb;0]=0.5]

e:(ofi q0)`e
/ row 2: bid same (b>=pb: +200, b<=pb: -300), ask up (a<=pa: no, a>=pa: +100) -> -100+100 = 0
/ row 3: bid up (+100), ask same (-400 +100) -> 100-400+100 = -200
check["ofi";e~0 0 -200f]

tr:([] time:(`timestamp$d)+09:30:02.000000000; sym:`AAPL; price:101; size:50; side:1h)
j:tradesWithQuotes[tr;q0]
check["prevailing quote is strictly before the trade";(j[`bid;0]=100) and j[`ask;0]=101]

g:grid[`AAPL;d;1]
check["grid covers the session";(23400=count g) and (last g`time)=(`timestamp$d)+16:00:00.000000000]

f:features[q0;tr;3#g;1 10]
check["features have labels";all `fwd1`fwd10 in cols f]
check["first forward label";f[`fwd1;0]=0.5]

-1 $[failures=0;"all analytics tests passed";string[failures]," failures"];
exit failures
