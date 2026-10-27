import { useState } from "react";

export interface Column<T> {
  key: keyof T & string;
  label: string;
  format?: (value: T[keyof T]) => string;
  numeric?: boolean;
}

/** A data table whose column headers are buttons that sort and announce the order. */
export function SortableTable<T extends Record<string, unknown>>({
  caption,
  columns,
  rows,
  initial,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  initial: keyof T & string;
}) {
  const [sortKey, setSortKey] = useState<keyof T & string>(initial);
  const [descending, setDescending] = useState(true);
  const sorted = rows.slice().sort((a, b) => {
    const x = a[sortKey];
    const y = b[sortKey];
    const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    return descending ? -order : order;
  });
  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                scope="col"
                key={c.key}
                aria-sort={sortKey === c.key ? (descending ? "descending" : "ascending") : "none"}
                className={c.numeric ? "numeric" : undefined}
              >
                <button
                  type="button"
                  className="sort"
                  onClick={() => {
                    if (sortKey === c.key) setDescending((d) => !d);
                    else {
                      setSortKey(c.key);
                      setDescending(true);
                    }
                  }}
                >
                  {c.label}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? "numeric" : undefined}>
                  {c.format ? c.format(row[c.key]) : String(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
