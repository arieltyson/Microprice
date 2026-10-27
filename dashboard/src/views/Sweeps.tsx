import { EmptyState } from "../components/EmptyState";
import { Panel } from "../components/Panel";
import { copy } from "../copy";
import { formatCount, formatRatio, formatUsdFromTicks } from "../format";
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

export function Sweeps() {
  const result = useJson<SweepResponse>("/api/sweeps", (d) => !d.top?.length);
  if (result.state === "loading") return <Panel title="Parameter sweep"><p role="status">Loading results.</p></Panel>;
  if (result.state === "error") return <Panel title="Parameter sweep"><EmptyState message={copy.sweeps.error} /></Panel>;
  if (result.state === "empty") return <Panel title="Parameter sweep"><EmptyState message={copy.sweeps.empty} /></Panel>;
  const d = result.data;
  return (
    <Panel title="Parameter sweep">
      <p className="lede">
        {formatCount(d.parameter_sets)} parameter sets, {formatCount(d.backtests)} backtests. Best Sharpe ratio{" "}
        {formatRatio(d.best_raw_sharpe)} per minute before deflation; probability that it beats the best of{" "}
        {formatCount(d.parameter_sets)} unskilled trials: {formatRatio(d.best_deflated_sharpe)}.
      </p>
      <SortableTable
        caption="Top parameter sets by raw Sharpe ratio, with their deflated Sharpe ratio"
        initial="sharpe_1min"
        columns={[
          { key: "gamma", label: "Gamma", numeric: true, format: ratio },
          { key: "kappa", label: "Kappa", numeric: true, format: ratio },
          { key: "tau_s", label: "Tau (s)", numeric: true, format: ratio },
          { key: "alpha", label: "Forecast weight", numeric: true, format: ratio },
          { key: "beta", label: "Sentiment weight", numeric: true, format: ratio },
          { key: "latency_ms", label: "Latency (ms)", numeric: true, format: ratio },
          { key: "sharpe_1min", label: "Sharpe (raw, 1-min)", numeric: true, format: ratio },
          { key: "deflated_sharpe", label: "Deflated Sharpe", numeric: true, format: ratio },
          { key: "pnl_ticks", label: "P&L", numeric: true, format: (v) => formatUsdFromTicks(Number(v)) },
        ]}
        rows={d.top}
      />
    </Panel>
  );
}
