// Every user-facing string, in one place. Copy states things once, in plain
// sentences, without exclamation marks. There is deliberately no message for a
// profitable run or a P&L threshold: profit and loss get the same treatment.
export const copy = {
  appName: "Microprice",
  skipLink: "Skip to main content",
  nav: { live: "Live", backtests: "Backtests", sweeps: "Sweeps" },
  live: {
    empty: "No replay is running. Start one to stream a held-out session from the gateway.",
    demoEmpty:
      "This is a static demo. Start the replay to play back a recorded held-out session: NVDA on 22 October, signal strategy, one point every five seconds.",
    start: "Start replay",
    stop: "Stop replay",
    connecting: "Connecting to the gateway.",
    disconnected: "Gateway disconnected. Run make gateway, then start the replay again.",
    ended: "Replay finished. The figures below are final for this session.",
    gap: "Feed gap: no data for this interval. It is not drawn as zero.",
  },
  backtests: {
    empty: "No held-out results yet. Run make results to produce them.",
    error: "Could not load backtest results from the gateway.",
  },
  sweeps: {
    empty: "No sweep results yet. Run make sweep to produce them.",
    error: "Could not load sweep results from the gateway.",
  },
  settings: { theme: "Theme", system: "Match system", light: "Light", dark: "Dark" },
} as const;
