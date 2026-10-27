import type { Level } from "../store";
import { formatCount, formatPrice } from "../format";

interface LadderProps {
  bids: readonly Level[];
  asks: readonly Level[];
  micro: number | null;
  lastTrade: number | null;
  caption?: string;
}

/**
 * The signature component: prices, resting size per side, where the micro-price
 * sits between the best bid and ask, and the last trade. It is a real table so
 * screen readers announce row and column headers. Depth beyond the levels
 * shown is not implied to be zero.
 */
export function OrderBookLadder({ bids, asks, micro, lastTrade, caption = "Order book, top five levels" }: LadderProps) {
  const maxSize = Math.max(1, ...bids.map((l) => l[1]), ...asks.map((l) => l[1]));
  const rows = [
    ...asks.slice().reverse().map(([price, size]) => ({ price, bid: null as number | null, ask: size as number | null })),
    ...bids.map(([price, size]) => ({ price, bid: size as number | null, ask: null as number | null })),
  ];
  const bestBid = bids[0]?.[0];
  const bestAsk = asks[0]?.[0];
  return (
    <table className="ladder">
      <caption className="visually-hidden">
        {caption}.
        {micro !== null && bestBid !== undefined && bestAsk !== undefined
          ? ` Micro-price ${formatPrice(micro)}, between the best bid ${formatPrice(bestBid)} and best ask ${formatPrice(bestAsk)}.`
          : ""}
        {lastTrade !== null ? ` Last trade ${formatPrice(lastTrade)}.` : ""}
      </caption>
      <thead>
        <tr>
          <th scope="col">Bid size</th>
          <th scope="col">Price</th>
          <th scope="col">Ask size</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={`${row.price}-${row.bid === null ? "a" : "b"}`}>
            <td className="ladder__size ladder__size--bid">
              {row.bid !== null && (
                <>
                  <span className="ladder__bar" style={{ inlineSize: `${(100 * row.bid) / maxSize}%` }} aria-hidden="true" />
                  <span className="ladder__number">{formatCount(row.bid)}</span>
                </>
              )}
            </td>
            <th scope="row" className="ladder__price">
              {formatPrice(row.price)}
              {lastTrade === row.price && <span className="ladder__trade"> (last trade)</span>}
            </th>
            <td className="ladder__size ladder__size--ask">
              {row.ask !== null && (
                <>
                  <span className="ladder__bar" style={{ inlineSize: `${(100 * row.ask) / maxSize}%` }} aria-hidden="true" />
                  <span className="ladder__number">{formatCount(row.ask)}</span>
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
      {micro !== null && (
        <tfoot>
          <tr>
            <th scope="row" colSpan={2}>
              Micro-price
            </th>
            <td className="ladder__micro">{formatPrice(micro)}</td>
          </tr>
        </tfoot>
      )}
    </table>
  );
}
