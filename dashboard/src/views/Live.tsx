import { useMemo, useSyncExternalStore } from "react";
import { ChartFigure, type ChartSeries } from "../components/ChartFigure";
import { EmptyState } from "../components/EmptyState";
import { MetricTile } from "../components/MetricTile";
import { OrderBookLadder } from "../components/OrderBookLadder";
import { Panel } from "../components/Panel";
import { DEMO, endpoints } from "../config";
import { copy } from "../copy";
import { formatClock, formatCount, formatPrice, formatSigned, formatUsdFromTicks } from "../format";
import { liveStore } from "../store";

const gatewayUrl = (): string => {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/live`;
};

export function Live({ themeKey }: { themeKey: string }) {
  const state = useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshot);
  const latest = state.latest;

  const pnlSeries = useMemo<ChartSeries[]>(
    () => [
      { label: "Spread capture", values: state.spreadCapture, color: "bid" },
      { label: "Inventory P&L", values: state.inventoryPnl, color: "ask", dash: [6, 4] },
    ],
    [state.spreadCapture, state.inventoryPnl],
  );
  const inventorySeries = useMemo<ChartSeries[]>(
    () => [{ label: "Inventory (shares)", values: state.inventory, color: "accent" }],
    [state.inventory],
  );

  const running = state.status === "live" || state.status === "connecting";
  const control = running ? (
    <button type="button" className="button button--secondary" onClick={() => liveStore.disconnect()}>
      {copy.live.stop}
    </button>
  ) : (
    <button
      type="button"
      className="button"
      onClick={() => (DEMO ? void liveStore.playRecorded(endpoints.replay) : liveStore.connect(gatewayUrl()))}
    >
      {copy.live.start}
    </button>
  );

  if (state.status === "idle") {
    return (
      <Panel title="Live replay">
        <EmptyState message={DEMO ? copy.live.demoEmpty : copy.live.empty} action={control} />
      </Panel>
    );
  }

  const spread = latest ? latest.spreadCapture : 0;
  const equity = latest ? latest.equity : 0;
  const statusText =
    state.status === "connecting"
      ? copy.live.connecting
      : state.status === "disconnected"
        ? copy.live.disconnected
        : state.status === "ended"
          ? copy.live.ended
          : state.meta
            ? `${state.meta.symbol} on ${state.meta.date}, ${state.meta.variant} strategy, ${latest ? formatClock(latest.t) : ""}`
            : "";

  return (
    <>
      <Panel title="Session" actions={control}>
        <p className="status" role="status" aria-live="polite">
          {statusText}
        </p>
        {latest && (
          <dl className="metrics">
            <MetricTile label="P&L" value={formatUsdFromTicks(equity)} sign={Math.sign(equity)} />
            <MetricTile label="Spread capture" value={formatUsdFromTicks(spread)} sign={Math.sign(spread)} />
            <MetricTile label="Inventory P&L" value={formatUsdFromTicks(equity - spread)} sign={Math.sign(equity - spread)} />
            <MetricTile label="Inventory" value={`${formatSigned(latest.inventory)} shares`} />
            <MetricTile label="Fills" value={formatCount(state.fills.length)} />
          </dl>
        )}
        {latest?.gap && <p className="gap-note">{copy.live.gap}</p>}
      </Panel>
      {latest && (
        <div className="grid">
          <Panel title="P&L by source">
            <ChartFigure
              title="Cumulative P&L split into spread capture and inventory P&L"
              summary={`Spread capture ${formatUsdFromTicks(spread)}, inventory P&L ${formatUsdFromTicks(equity - spread)} at ${formatClock(latest.t)}.`}
              times={state.times}
              series={pnlSeries}
              format={(v) => formatUsdFromTicks(v)}
              formatTime={formatClock}
              themeKey={themeKey}
            />
          </Panel>
          <Panel title="Order book">
            <OrderBookLadder bids={latest.bids} asks={latest.asks} micro={latest.micro} lastTrade={latest.lastTrade} />
          </Panel>
          <Panel title="Inventory">
            <ChartFigure
              title="Inventory over time"
              summary={`Inventory is ${formatSigned(latest.inventory)} shares at ${formatClock(latest.t)}.`}
              times={state.times}
              series={inventorySeries}
              format={(v) => formatSigned(v)}
              formatTime={formatClock}
              themeKey={themeKey}
            />
          </Panel>
          <Panel title="Recent fills" inset>
            <div className="table-scroll">
              <table className="data-table">
                <caption className="visually-hidden">Most recent fills, newest first</caption>
                <thead>
                  <tr>
                    <th scope="col">Time</th>
                    <th scope="col">Side</th>
                    <th scope="col">Price</th>
                    <th scope="col">Shares</th>
                  </tr>
                </thead>
                <tbody>
                  {state.fills.slice(-12).reverse().map((f, i) => (
                    <tr key={`${f.t}-${i}`}>
                      <td>{formatClock(f.t)}</td>
                      <td className={f.side > 0 ? "side side--buy" : "side side--sell"}>{f.side > 0 ? "Bought" : "Sold"}</td>
                      <td>{formatPrice(f.price)}</td>
                      <td>{formatCount(f.qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
