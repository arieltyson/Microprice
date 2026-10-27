import { EmptyState } from "../components/EmptyState";
import { Panel } from "../components/Panel";
import { endpoints } from "../config";
import { copy } from "../copy";
import { formatCount, formatDecimal, formatRatio, formatUsdFromTicks } from "../format";
import { SortableTable } from "./SortableTable";
import { useJson } from "./useJson";

interface SweepResponse {
  parameter_sets: number;
  backtests: number;
  best_raw_sharpe: number;
  best_deflated_sharpe: number;
  top: Record<string, number>[];
}

const ratio = (v: unknown) => formatRatio(Number(v));
const param = (v: unknown) => formatDecimal(Number(v));
const probability = (v: unknown) => (v == null ? "n/a" : Number(v).toFixed(3));

export function Sweeps() {
  const result = useJson<SweepResponse>(endpoints.sweeps, (d) => !d.top?.length);
  if (result.state === "loading") return <Panel title="Parameter sweep"><p role="status">Loading results.</p></Panel>;
  if (result.state === "error") return <Panel title="Parameter sweep"><EmptyState message={copy.sweeps.error} /></Panel>;
  if (result.state === "empty") return <Panel title="Parameter sweep"><EmptyState message={copy.sweeps.empty} /></Panel>;
  const d = result.data;
  return (
    <Panel title="Parameter sweep">
      <p className="lede">
        {formatCount(d.parameter_sets)} parameter sets, {formatCount(d.backtests)} backtests. Best Sharpe ratio{" "}
        {formatDecimal(d.best_raw_sharpe)} per minute before deflation. The deflated Sharpe ratio, the probability
        that it beats the best of {formatCount(d.parameter_sets)} unskilled trials, is {d.best_deflated_sharpe.toFixed(3)}:
        a half-hour selection window cannot prove skill on its own, so the Backtests view compares strategies on
        untouched days.
      </p>
      <SortableTable
        caption="Top parameter sets by raw Sharpe ratio, with their deflated Sharpe ratio"
        initial="sharpe_1min"
        columns={[
          { key: "gamma", label: "Gamma", numeric: true, format: param },
          { key: "kappa", label: "Kappa", numeric: true, format: param },
          { key: "tau_s", label: "Tau (s)", numeric: true, format: param },
          { key: "alpha", label: "Forecast weight", numeric: true, format: param },
          { key: "beta", label: "Sentiment weight", numeric: true, format: param },
          { key: "quote_lots", label: "Quote lots", numeric: true, format: param },
          { key: "max_inventory_lots", label: "Max inventory (lots)", numeric: true, format: param },
          { key: "latency_ms", label: "Latency (ms)", numeric: true, format: param },
          { key: "sharpe_1min", label: "Sharpe (raw, 1-min)", numeric: true, format: ratio },
          { key: "deflated_sharpe", label: "Deflated Sharpe (probability)", numeric: true, format: probability },
          { key: "pnl_ticks", label: "P&L", numeric: true, format: (v) => formatUsdFromTicks(Number(v)) },
        ]}
        rows={d.top}
      />
    </Panel>
  );
}
