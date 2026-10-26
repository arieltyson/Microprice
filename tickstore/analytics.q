/ Order book analytics computed next to the data.
/ Each function has a pandas twin with the same name in research/microprice/store.py
/ and research/microprice/features.py; tests check that both agree.

/ Mid, spread, level-1 imbalance and the micro-price (Stoikov 2018), in ticks.
withMicro:{[q]
  update mid:0.5*bid+ask, spread:ask-bid, imb:(bsize-asize)%bsize+asize,
    micro:((bid*asize)+ask*bsize)%bsize+asize from q
  }

/ Order flow imbalance of each quote update (Cont, Kukanov and Stoikov 2014):
/ e = 1{b>=b'}q^b - 1{b<=b'}q^b' - 1{a<=a'}q^a + 1{a>=a'}q^a', primes marking the previous update.
ofi:{[q]
  q:update pb:prev bid, pbs:prev bsize, pa:prev ask, pas:prev asize by sym from q;
  q:update e:0^(((bid>=pb)*bsize)-(bid<=pb)*pbs)-(((ask<=pa)*asize)-(ask>=pa)*pas) from q;
  delete pb,pbs,pa,pas from q
  }

/ Prevailing quote for each trade: the last quote strictly before the trade, so
/ the book the trade itself produced is not used to describe it.
tradesWithQuotes:{[tr;q]
  t:update qtime:time-1 from tr;
  r:aj[`sym`qtime;t;select sym, qtime:time, bid, ask, bsize, asize from q];
  delete qtime from r
  }

/ A regular time grid for one symbol-day between 09:30 and 16:00.
grid:{[s;day;stepSeconds]
  n:`long$23400%stepSeconds;
  ([] sym:n#s; time:(`timestamp$day)+09:30:00.000000000+`timespan$`long$1e9*stepSeconds*1+til n)
  }

/ As-of sample of columns at grid times shifted by `shift` seconds (negative looks back).
sampleAt:{[g;t;cols;shift]
  g2:update time:time+`timespan$`long$1e9*shift from g;
  ?[aj[`sym`time;g2;t];();0b;cols!cols]
  }

/ Level-1 features and forward mid-price labels on a grid. Window sums use
/ cumulative sums sampled at both ends of the window.
features:{[q;tr;g;horizons]
  qq:update cofi:sums e by sym from ofi withMicro `sym`time xasc q;
  tv:update csv:sums size*side by sym from `sym`time xasc tr;
  now:sampleAt[g;qq;`mid`micro`spread`imb`cofi;0];
  f:g,'select spread, imb, microDev:micro-mid, mid from now;
  f:f,'([] ofi1:now[`cofi]-sampleAt[g;qq;enlist`cofi;-1]`cofi;
           ofi10:now[`cofi]-sampleAt[g;qq;enlist`cofi;-10]`cofi);
  vol10:0^(sampleAt[g;tv;enlist`csv;0]`csv)-sampleAt[g;tv;enlist`csv;-10]`csv;
  f:update tradeImb10:vol10, ret10:mid-sampleAt[g;qq;enlist`mid;-10]`mid, rv60:60 mdev 0^deltas mid from f;
  labels:{[g;qq;m;h] (`$"fwd",string h)!enlist (sampleAt[g;qq;enlist`mid;h]`mid)-m}[g;qq;f`mid] each horizons;
  f,'flip raze labels
  }
