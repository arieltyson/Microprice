import { useEffect, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { copy } from "./copy";
import { applyTheme, savedTheme, saveTheme, type ThemeChoice } from "./theme";
import { Backtests } from "./views/Backtests";
import { Live } from "./views/Live";
import { Sweeps } from "./views/Sweeps";

export function App() {
  const [choice, setChoice] = useState<ThemeChoice>(savedTheme);
  const [themeKey, setThemeKey] = useState(() => applyTheme(choice));

  useEffect(() => {
    const update = () => setThemeKey(applyTheme(choice));
    update();
    const queries = [matchMedia("(prefers-color-scheme: dark)"), matchMedia("(prefers-contrast: more)")];
    queries.forEach((q) => q.addEventListener("change", update));
    return () => queries.forEach((q) => q.removeEventListener("change", update));
  }, [choice]);

  return (
    <BrowserRouter>
      <a className="skip-link" href="#main">
        {copy.skipLink}
      </a>
      <header className="app-header">
        <a className="brand" href="/">
          <img src="/favicon.svg" alt="" width={24} height={24} />
          <span>{copy.appName}</span>
        </a>
        <nav aria-label="Views">
          <ul className="nav">
            <li><NavLink to="/" end>{copy.nav.live}</NavLink></li>
            <li><NavLink to="/backtests">{copy.nav.backtests}</NavLink></li>
            <li><NavLink to="/sweeps">{copy.nav.sweeps}</NavLink></li>
          </ul>
        </nav>
        <label className="theme-select">
          <span>{copy.settings.theme}</span>
          <select
            value={choice}
            onChange={(e) => {
              const next = e.target.value as ThemeChoice;
              saveTheme(next);
              setChoice(next);
            }}
          >
            <option value="system">{copy.settings.system}</option>
            <option value="light">{copy.settings.light}</option>
            <option value="dark">{copy.settings.dark}</option>
          </select>
        </label>
      </header>
      <main id="main" tabIndex={-1}>
        <h1 className="visually-hidden">{copy.appName}</h1>
        <Routes>
          <Route path="/" element={<Live themeKey={themeKey} />} />
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/sweeps" element={<Sweeps />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
