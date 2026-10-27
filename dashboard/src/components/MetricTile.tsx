interface MetricTileProps {
  label: string;
  value: string;
  sign?: number; // carries a glyph and a position cue as well as colour
}

export function MetricTile({ label, value, sign }: MetricTileProps) {
  const tone = sign === undefined || sign === 0 ? "" : sign > 0 ? " metric--up" : " metric--down";
  return (
    <div className={`metric${tone}`}>
      <dt className="metric__label">{label}</dt>
      <dd className="metric__value">{value}</dd>
    </div>
  );
}
