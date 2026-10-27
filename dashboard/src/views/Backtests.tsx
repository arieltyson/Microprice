import { EmptyState } from "../components/EmptyState";
import { Panel } from "../components/Panel";
import { endpoints } from "../config";
import { copy } from "../copy";
import { formatCount, formatRatio, formatUsdFromTicks } from "../format";
import { SortableTable } from "./SortableTable";
import { useJson } from "./useJson";

interface SessionRow extends Record<string, unknown> {
  variant: string;
  symbol: string;
  date: string;
  pnl_ticks: number;
  spread_capture_ticks: number;
  inventory_pnl_ticks: number;
  sharpe_annualized_1min: number;
  fills: number;
  markout_10s: number;
}

interface SummaryMetrics {
  pnl_usd: number;
  sharpe: number;
  markout_10s: number;
  fills: number;
}

interface SummaryRow extends SummaryMetrics, Record<string, unknown> {
  variant: string;
}

interface Holdout {
  sessions: SessionRow[];
  summary: Record<string, SummaryMetrics>;
}

const num = (v: unknown) => formatRatio(Number(v));

export function Backtests() {
  const result = useJson<Holdout>(endpoints.backtests, (d) => !d.sessions?.length);
  if (result.state === "loading") return <Panel title="Held-out backtests"><p role="status">Loading results.</p></Panel>;
  if (result.state === "error") return <Panel title="Held-out backtests"><EmptyState message={copy.backtests.error} /></Panel>;
  if (result.state === "empty") return <Panel title="Held-out backtests"><EmptyState message={copy.backtests.empty} /></Panel>;
  const { sessions, summary } = result.data;
  return (
    <>
      <Panel title="Held-out comparison">
        <SortableTable<SummaryRow>
          caption="Baseline and signal strategies on held-out days, all symbols combined"
          initial="sharpe"
          columns={[
            { key: "variant", label: "Strategy" },
            { key: "pnl_usd", label: "P&L", numeric: true, format: (v) => formatUsdFromTicks(Number(v) * 100) },
            { key: "sharpe", label: "Sharpe (annualized, 1-min)", numeric: true, format: num },
            { key: "markout_10s", label: "10 s markout (ticks)", numeric: true, format: num },
            { key: "fills", label: "Fills", numeric: true, format: (v) => formatCount(Number(v)) },
          ]}
          rows={Object.entries(summary).map(([variant, s]): SummaryRow => ({ ...s, variant }))}
        />
      </Panel>
      <Panel title="Sessions">
        <SortableTable<SessionRow>
          caption="Per symbol and day results on held-out days"
          initial="pnl_ticks"
          columns={[
            { key: "variant", label: "Strategy" },
            { key: "symbol", label: "Symbol" },
            { key: "date", label: "Date" },
            { key: "pnl_ticks", label: "P&L", numeric: true, format: (v) => formatUsdFromTicks(Number(v)) },
            { key: "spread_capture_ticks", label: "Spread capture", numeric: true, format: (v) => formatUsdFromTicks(Number(v)) },
            { key: "inventory_pnl_ticks", label: "Inventory P&L", numeric: true, format: (v) => formatUsdFromTicks(Number(v)) },
            { key: "fills", label: "Fills", numeric: true, format: (v) => formatCount(Number(v)) },
            { key: "markout_10s", label: "10 s markout", numeric: true, format: num },
          ]}
          rows={sessions}
        />
      </Panel>
    </>
  );
}
