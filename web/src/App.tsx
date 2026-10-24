import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AskBox } from "./components/AskBox";
import JobDetail from "./pages/JobDetail";
import Jobs from "./pages/Jobs";
import Login from "./pages/Login";
import Media from "./pages/Media";
import NewJob from "./pages/NewJob";
import { useSession } from "./session";

export default function App() {
  const { me, loading, signOut } = useSession();
  if (loading) return <div className="page muted">Loading…</div>;
  if (!me) return <Login />;
  const employer = me.user_class === "employer";
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">Field Assistant</NavLink>
        <nav>
          <NavLink to="/" end>Jobs</NavLink>
          {employer && <NavLink to="/media">Media</NavLink>}
          <NavLink to="/ask">Ask docs</NavLink>
        </nav>
        <span className="who">{me.username} · {me.user_class} · {me.company.name}</span>
        <button className="link signout" onClick={signOut}>Sign out</button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Jobs />} />
          <Route path="/jobs/new" element={employer ? <NewJob /> : <Navigate to="/" />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/media" element={employer ? <Media /> : <Navigate to="/" />} />
          <Route path="/ask" element={<div className="page"><AskBox /></div>} />
          <Route path="*" element={<div className="page"><h1>Not found</h1></div>} />
        </Routes>
      </main>
    </div>
  );
}
