import { useId, type ReactNode } from "react";

interface PanelProps {
  title: string;
  children: ReactNode;
  inset?: boolean;
  actions?: ReactNode;
}

/** The one container every grouped region uses. */
export function Panel({ title, children, inset = false, actions }: PanelProps) {
  const id = useId();
  return (
    <section className={inset ? "panel panel--inset" : "panel"} aria-labelledby={id}>
      <header className="panel__header">
        <h2 id={id} className="panel__title">
          {title}
        </h2>
        {actions}
      </header>
      {children}
    </section>
  );
}
