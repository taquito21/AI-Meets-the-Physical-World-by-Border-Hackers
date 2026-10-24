import { NavLink, Route, Routes } from "react-router-dom";
import { ChartColumn, CircleUserRound, ClipboardCheck, FlaskConical, Package, TriangleAlert } from "lucide-react";
import { LanguageSwitch } from "./components/LanguageSwitch";
import { t } from "./i18n";
import { useSession } from "./session";
import Login from "./pages/Login";
import Account from "./pages/Account";
import Home from "./pages/Home";
import Catalog from "./pages/Catalog";
import ProductDetail from "./pages/ProductDetail";
import Inspection from "./pages/Inspection";
import Summary from "./pages/Summary";
import Supervisor from "./pages/Supervisor";
import Findings from "./pages/Findings";
import ImportStudio from "./pages/ImportStudio";
import Passport from "./pages/Passport";
import Dashboard from "./pages/Dashboard";
import Render from "./pages/Render";

export default function App() {
  const { label, name, role, health, user, ready } = useSession();
  if (window.location.pathname.startsWith("/render/")) {
    return <Routes><Route path="/render/:revisionId" element={<Render />} /></Routes>;
  }
  if (!ready) return <div className="page muted">{t("Loading…")}</div>;
  if (!user) return <Login />;
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">{label}</NavLink>
        <nav>
          <NavLink to="/catalog"><Package aria-hidden /><span>{t("Equipment")}</span></NavLink>
          {role === "supervisor" && <NavLink to="/supervisor"><ClipboardCheck aria-hidden /><span>{t("Review")}</span></NavLink>}
          <NavLink to="/findings"><TriangleAlert aria-hidden /><span>{t("Problems")}</span></NavLink>
          <NavLink to="/dashboard"><ChartColumn aria-hidden /><span>{t("Dashboard")}</span></NavLink>
        </nav>
        <NavLink to="/account" className="who" title={t("My account")} aria-label={t("My account")}>
          <CircleUserRound aria-hidden /><span>{name}</span>
        </NavLink>
        <LanguageSwitch />
      </header>
      {health?.storage === "ephemeral" && (
        <div className="test-banner"><FlaskConical aria-hidden /> {t("Temporary test deployment: data is not permanent and may reset at any time.")}</div>
      )}
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/catalog" element={<Catalog />} />
          <Route path="/products/:revisionId" element={<ProductDetail />} />
          <Route path="/inspections/:id" element={<Inspection />} />
          <Route path="/inspections/:id/summary" element={<Summary />} />
          <Route path="/supervisor" element={<Supervisor />} />
          <Route path="/supervisor/:id" element={<Summary review />} />
          <Route path="/findings" element={<Findings />} />
          <Route path="/import" element={<ImportStudio />} />
          <Route path="/p/:serial" element={<Passport />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/account" element={<Account />} />
          <Route path="*" element={<div className="page"><h1>{t("Page not found")}</h1><NavLink to="/">{t("Go to the start")}</NavLink></div>} />
        </Routes>
      </main>
    </div>
  );
}
