// All numbers on screen go through these formatters, so units and signs are consistent.

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", signDisplay: "exceptZero" });
const price = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0, signDisplay: "exceptZero" });
const plain = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const ratio = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, signDisplay: "exceptZero" });
const time = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "UTC" });

/** Ticks of 0.01 USD to a signed dollar amount. */
export const formatUsdFromTicks = (ticks: number): string => usd.format(ticks / 100).replace("-", "−");
/** A price in ticks to dollars and cents. */
export const formatPrice = (ticks: number): string => price.format(ticks / 100);
export const formatSigned = (value: number): string => integer.format(value).replace("-", "−");
export const formatCount = (value: number): string => plain.format(value);
export const formatRatio = (value: number): string => ratio.format(value).replace("-", "−");
/** Seconds after midnight to HH:MM:SS (the session clock is exchange time). */
export const formatClock = (secondsAfterMidnight: number): string => time.format(new Date(secondsAfterMidnight * 1000));
