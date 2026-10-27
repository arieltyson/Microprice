// Static demo builds (VITE_DEMO=true) read recorded files instead of the gateway.
export const DEMO = import.meta.env.VITE_DEMO === "true";
const base = import.meta.env.BASE_URL;

export const endpoints = {
  backtests: DEMO ? `${base}demo/backtests.json` : "/api/backtests",
  sweeps: DEMO ? `${base}demo/sweeps.json` : "/api/sweeps",
  replay: `${base}demo/replay.json`,
};

export const assetUrl = (path: string): string => `${base}${path}`;
