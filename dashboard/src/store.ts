// Live replay state, fed by the gateway's WebSocket and read by React through
// useSyncExternalStore. Messages are queued and applied once per animation
// frame, so React re-renders at most once per frame however fast data arrives.

export type Level = readonly [price: number, size: number];

export interface FillMessage {
  t: number;
  side: 1 | -1;
  price: number;
  qty: number;
}

export interface TickMessage {
  type: "tick";
  t: number; // seconds after midnight
  mid: number | null;
  micro: number | null;
  equity: number; // ticks
  spreadCapture: number; // ticks
  inventory: number; // shares
  bids: Level[];
  asks: Level[];
  lastTrade: number | null;
  gap: boolean;
  fills: FillMessage[];
}

export interface MetaMessage {
  type: "meta";
  symbol: string;
  date: string;
  variant: string;
}

export type GatewayMessage = TickMessage | MetaMessage | { type: "end" };

export type Status = "idle" | "connecting" | "live" | "ended" | "disconnected";

export interface LiveState {
  status: Status;
  meta: MetaMessage | null;
  times: number[];
  equity: (number | null)[];
  spreadCapture: (number | null)[];
  inventoryPnl: (number | null)[];
  inventory: (number | null)[];
  latest: TickMessage | null;
  fills: FillMessage[];
  gaps: number;
}

export const MAX_POINTS = 4 * 3600; // bounded history: four hours at one point per second
const MAX_FILLS = 200;

export function emptyState(): LiveState {
  return {
    status: "idle",
    meta: null,
    times: [],
    equity: [],
    spreadCapture: [],
    inventoryPnl: [],
    inventory: [],
    latest: null,
    fills: [],
    gaps: 0,
  };
}

/** Pure reducer: applies a batch of gateway messages to the state. */
export function reduce(state: LiveState, messages: GatewayMessage[]): LiveState {
  if (messages.length === 0) return state;
  const next: LiveState = {
    ...state,
    times: state.times.slice(),
    equity: state.equity.slice(),
    spreadCapture: state.spreadCapture.slice(),
    inventoryPnl: state.inventoryPnl.slice(),
    inventory: state.inventory.slice(),
    fills: state.fills.slice(),
  };
  for (const message of messages) {
    if (message.type === "meta") {
      Object.assign(next, emptyState(), { status: "live", meta: message });
    } else if (message.type === "end") {
      next.status = "ended";
    } else {
      next.status = "live";
      next.times.push(message.t);
      // A gap is stored as null so charts break the line instead of drawing zero.
      next.equity.push(message.gap ? null : message.equity);
      next.spreadCapture.push(message.gap ? null : message.spreadCapture);
      next.inventoryPnl.push(message.gap ? null : message.equity - message.spreadCapture);
      next.inventory.push(message.gap ? null : message.inventory);
      next.gaps += message.gap ? 1 : 0;
      next.latest = message;
      next.fills.push(...message.fills);
    }
  }
  const excess = next.times.length - MAX_POINTS;
  if (excess > 0) {
    for (const key of ["times", "equity", "spreadCapture", "inventoryPnl", "inventory"] as const) {
      next[key].splice(0, excess);
    }
  }
  if (next.fills.length > MAX_FILLS) next.fills.splice(0, next.fills.length - MAX_FILLS);
  return next;
}

export class LiveStore {
  private state: LiveState = emptyState();
  private listeners = new Set<() => void>();
  private queue: GatewayMessage[] = [];
  private frame = 0;
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): LiveState => this.state;

  connect(url: string): void {
    this.disconnect();
    this.set({ ...emptyState(), status: "connecting" });
    const socket = new WebSocket(url);
    this.socket = socket;
    socket.onmessage = (event) => this.enqueue(JSON.parse(String(event.data)) as GatewayMessage);
    socket.onclose = () => {
      if (this.socket === socket && this.state.status !== "ended") this.set({ ...this.state, status: "disconnected" });
    };
  }

  /** Plays a recorded session (static demo builds have no gateway to connect to). */
  async playRecorded(url: string, intervalMs = 40): Promise<void> {
    this.disconnect();
    this.set({ ...emptyState(), status: "connecting" });
    let messages: GatewayMessage[];
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(String(response.status));
      messages = (await response.json()) as GatewayMessage[];
    } catch {
      this.set({ ...this.state, status: "disconnected" });
      return;
    }
    let next = 0;
    this.timer = setInterval(() => {
      if (next >= messages.length) {
        if (this.timer) clearInterval(this.timer);
        this.timer = null;
        return;
      }
      this.enqueue(messages[next++]);
    }, intervalMs);
  }

  disconnect(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (this.socket) {
      const socket = this.socket;
      this.socket = null;
      socket.close();
    }
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.queue = [];
  }

  enqueue(message: GatewayMessage): void {
    this.queue.push(message);
    if (!this.frame) {
      this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        const batch = this.queue;
        this.queue = [];
        this.set(reduce(this.state, batch));
      });
    }
  }

  private set(next: LiveState): void {
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}

export const liveStore = new LiveStore();
