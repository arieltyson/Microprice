import { useEffect, useId, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { currentColor } from "../theme";

export interface ChartSeries {
  label: string;
  values: (number | null)[];
  color: "bid" | "ask" | "accent" | "textSecondary";
  dash?: number[];
}

interface ChartFigureProps {
  title: string;
  summary: string; // read by screen readers in place of the canvas
  times: number[];
  series: ChartSeries[];
  format: (value: number) => string;
  formatTime: (t: number) => string;
  themeKey: string;
}

/**
 * A uPlot chart with a text summary and a data table holding the same values.
 * The canvas is hidden from assistive technology; the table is the accessible
 * alternative. Chart data updates in place, without re-rendering React.
 */
export function ChartFigure({ title, summary, times, series, format, formatTime, themeKey }: ChartFigureProps) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();
  const labels = series.map((s) => s.label).join("|");

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const axis = { stroke: currentColor("textSecondary"), grid: { stroke: currentColor("separator"), width: 1 } };
    const options: uPlot.Options = {
      width: element.clientWidth || 600,
      height: 220,
      legend: { show: true },
      cursor: { drag: { x: false, y: false } },
      scales: { x: { time: false } },
      axes: [
        { ...axis, values: (_u, ticks) => ticks.map(formatTime) },
        { ...axis, values: (_u, ticks) => ticks.map(format), size: 80 },
      ],
      series: [
        { label: "Time", value: (_u, v) => (v == null ? "" : formatTime(v)) },
        ...series.map((s) => ({
          label: s.label,
          stroke: currentColor(s.color),
          width: 2,
          dash: s.dash,
          spanGaps: false, // feed gaps break the line instead of being interpolated
          value: (_u: uPlot, v: number | null) => (v == null ? "no data" : format(v)),
        })),
      ],
    };
    plot.current = new uPlot(options, [times, ...series.map((s) => s.values)] as uPlot.AlignedData, element);
    const resize = new ResizeObserver(() => plot.current?.setSize({ width: element.clientWidth, height: 220 }));
    resize.observe(element);
    return () => {
      resize.disconnect();
      plot.current?.destroy();
      plot.current = null;
    };
    // Rebuild only when the series definitions or theme change; data updates below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labels, themeKey]);

  useEffect(() => {
    plot.current?.setData([times, ...series.map((s) => s.values)] as uPlot.AlignedData, true);
  }, [times, series]);

  const recent = times.slice(-20).map((t, i, all) => {
    const index = times.length - all.length + i;
    return { t, values: series.map((s) => s.values[index]) };
  });

  return (
    <figure className="chart">
      <figcaption className="chart__caption">
        <span className="chart__title">{title}</span>
        <span className="chart__summary">{summary}</span>
      </figcaption>
      <div ref={host} className="chart__canvas" aria-hidden="true" />
      <button
        type="button"
        className="button button--secondary"
        aria-expanded={showTable}
        aria-controls={tableId}
        onClick={() => setShowTable((v) => !v)}
      >
        {showTable ? "Hide data table" : "Show data table"}
      </button>
      <div id={tableId} hidden={!showTable} className="chart__table">
        <table>
          <caption className="visually-hidden">{title}, most recent 20 points</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              {series.map((s) => (
                <th scope="col" key={s.label}>
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {recent.map((row) => (
              <tr key={row.t}>
                <th scope="row">{formatTime(row.t)}</th>
                {row.values.map((v, i) => (
                  <td key={series[i].label}>{v == null ? "No data (feed gap)" : format(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
