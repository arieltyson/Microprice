/ Loaders for feed capture files and LOBSTER files, and the HDB writer.
/ Usage: q tickstore/load.q -data data/synthetic -hdb tickstore/hdb

\l tickstore/schema.q

/ Reads a capture file of 48-byte little-endian records written by feed_capture.
/ Layout: type, side, symbol, reserved, ts, id, aggressor, price, qty, remaining.
loadCapture:{[file;day]
  c:("xxhijjjjii";1 1 2 4 8 8 8 8 4 4) 1: file;
  ([] time:(`timestamp$day)+`timespan$c 4;
      sym:syms -1+`long$c 2;
      typ:`char$c 0;
      side:`char$c 1;
      id:c 5;
      aggressor:c 6;
      price:c 7;
      qty:`long$c 8;
      remaining:`long$c 9)
  }

/ LOBSTER message file: time (s after midnight), type, id, size, price (USD x 10000), direction.
loadMessages:{[file]
  flip `secs`typ`id`size`price`dir!("FIJJJH";",") 0: file
  }

/ LOBSTER order book file, level 1: ask price, ask size, bid price, bid size.
loadBook:{[file]
  flip `ap`as`bp`bs!("JJJJ";",") 0: file
  }

toTime:{[day;secs] (`timestamp$day)+`timespan$`long$1e9*secs}

/ Builds the quote and trade tables for one symbol-day from a LOBSTER file pair.
lobsterTables:{[day;s;msgFile;bookFile]
  m:loadMessages msgFile;
  b:loadBook bookFile;
  t:toTime[day;m`secs];
  / An empty side is null rather than LOBSTER's sentinel price.
  q:([] time:t; sym:count[t]#s; bid:?[0<b`bs;(b`bp) div 100;0N]; ask:?[0<b`as;(b`ap) div 100;0N]; bsize:b`bs; asize:b`as);
  ex:where m[`typ]=4;
  tr:([] time:t ex; sym:count[ex]#s; price:(m[`price] ex) div 100; size:m[`size] ex; side:neg m[`dir] ex);
  (q;tr)
  }

/ Loads every symbol-day under <root>/<SYM>/<SYM>_<date>_..._message_1.csv into a
/ date-partitioned HDB. Each day is written once, with .Q.dpft enumerating sym and
/ applying the parted attribute.
loadLobsterTree:{[root;hdb]
  dirs:k where not (k:key root) like "*.*";
  msgs:raze {[root;s] f:` sv' (` sv root,s),'key ` sv root,s; f where f like "*message_1.csv"}[root] each dirs;
  info:{p:"_" vs last "/" vs string x; (`$p 0;"D"$p 1)} each msgs;
  {[hdb;msgs;info;d]
    sel:where d=info[;1];
    pairs:{[i;f] lobsterTables[i 1;i 0;f;`$ssr[string f;"message";"orderbook"]]}'[info sel;msgs sel];
    `quote set raze pairs[;0];
    `trade set raze pairs[;1];
    .Q.dpft[hdb;d;`sym] each `quote`trade;
    }[hdb;msgs;info] each distinct info[;1];
  count msgs
  }

if[`data in key .Q.opt .z.x;
  o:.Q.opt .z.x;
  n:loadLobsterTree[hsym `$first o`data;hsym `$first o`hdb];
  -1 "loaded ",string[n]," symbol-days";
  exit 0];
