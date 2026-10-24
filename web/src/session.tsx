// Signed-in person (worker or supervisor). The server keeps the session in an HttpOnly cookie and records every
// action under this person's name; the browser only mirrors who is signed in.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Health, type Role, type User } from "./api";
import { t } from "./i18n";

export type { Role };

interface Session {
  user: User | null; // null: signed out
  ready: boolean; // the first "who am I" answer has arrived
  name: string;
  role: Role;
  setUser: (u: User | null) => void;
  signOut: () => Promise<void>;
  health: Health | null;
  label: string;
  industry: string; // active scenario filter: "All" or an industry name (e.g. "Furniture", "Electrical")
  setIndustry: (i: string) => void;
}

const Ctx = createContext<Session | null>(null);

function stored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: keep in memory only */
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [industry, setIndustryState] = useState(() => stored("fep.industry", "All"));

  // Retry until the server answers (it may still be starting, or a serverless instance may be cold).
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const load = () => api.health().then((h) => { if (!stop) setHealth(h); })
      .catch(() => { if (!stop) timer = setTimeout(load, 5000); });
    load();
    return () => { stop = true; clearTimeout(timer); };
  }, []);

  useEffect(() => {
    api.me().then((r) => setUser(r.user)).catch(() => setUser(null)).finally(() => setReady(true));
    const signedOut = () => setUser(null);
    window.addEventListener("fep:signed-out", signedOut);
    return () => window.removeEventListener("fep:signed-out", signedOut);
  }, []);

  const label = t(health?.app_label ?? "Field Assistant");
  useEffect(() => {
    document.title = label;
  }, [label]);

  const value: Session = {
    user, ready, health, label, industry,
    name: user?.display_name ?? "",
    role: user?.role ?? "inspector",
    setUser,
    signOut: async () => {
      await api.logout().catch(() => undefined);
      setUser(null);
    },
    setIndustry: (i) => { setIndustryState(i); persist("fep.industry", i); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("SessionProvider missing");
  return s;
}
