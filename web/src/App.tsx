import { NavLink, Route, Routes } from "react-router-dom";
import { useSession } from "./session";
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
  const { label, name, role, health } = useSession();
  if (window.location.pathname.startsWith("/render/")) {
    return <Routes><Route path="/render/:revisionId" element={<Render />} /></Routes>;
  }
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">{label}</NavLink>
        <nav>
          <NavLink to="/catalog">Equipment</NavLink>
          <NavLink to="/supervisor">Review</NavLink>
          <NavLink to="/findings">Problems</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
        </nav>
        <span className="who" title="Change on the home screen">{name} · {role}</span>
      </header>
      {health?.storage === "ephemeral" && (
        <div className="test-banner">Temporary test deployment: data is not permanent and may reset at any time.</div>
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
          <Route path="*" element={<div className="page"><h1>Page not found</h1><NavLink to="/">Go to the start</NavLink></div>} />
        </Routes>
      </main>
    </div>
  );
}
