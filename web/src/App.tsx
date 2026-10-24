import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { BookOpen, ClipboardList, FolderOpen, LogOut } from "lucide-react";
import { AskBox } from "./components/AskBox";
import { LanguageSwitch } from "./components/LanguageSwitch";
import { t } from "./i18n";
import JobDetail from "./pages/JobDetail";
import Jobs from "./pages/Jobs";
import Login from "./pages/Login";
import Media from "./pages/Media";
import NewJob from "./pages/NewJob";
import { useSession } from "./session";

export default function App() {
  const { me, loading, signOut } = useSession();
  if (loading) return <div className="page muted">{t("Loading…")}</div>;
  if (!me) return <Login />;
  const employer = me.user_class === "employer";
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="FieldSight">
          <img src="/brand/fieldsight-mark.png" alt="" width={30} height={30} />
          <span>Field<span className="brand-sight">Sight</span></span>
        </NavLink>
        <nav>
          <NavLink to="/" end><ClipboardList aria-hidden /><span>{t(employer ? "Overview" : "My jobs")}</span></NavLink>
          {employer && <NavLink to="/media"><FolderOpen aria-hidden /><span>{t("Media")}</span></NavLink>}
          <NavLink to="/ask"><BookOpen aria-hidden /><span>{t("Ask docs")}</span></NavLink>
        </nav>
        <span className="who">{me.username} · {t(me.user_class)} · {me.company.name}</span>
        <LanguageSwitch />
        <button className="link signout with-icon" onClick={signOut}><LogOut aria-hidden />{t("Sign out")}</button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Jobs />} />
          <Route path="/jobs/new" element={employer ? <NewJob /> : <Navigate to="/" />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/media" element={employer ? <Media /> : <Navigate to="/" />} />
          <Route path="/ask" element={<div className="page"><AskBox /></div>} />
          <Route path="*" element={<div className="page"><h1>{t("Page not found")}</h1></div>} />
        </Routes>
      </main>
    </div>
  );
}
