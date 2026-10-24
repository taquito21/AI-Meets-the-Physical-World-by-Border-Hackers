// Lightweight demo identity (no authentication in the MVP). Names are recorded on every action.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Health } from "./api";
import { t } from "./i18n";

export type Role = "inspector" | "supervisor";

interface Session {
  name: string;
  role: Role;
  setName: (n: string) => void;
  setRole: (r: Role) => void;
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
  const [name, setNameState] = useState(() => stored("fep.name", "Inspector A"));
  const [role, setRoleState] = useState<Role>(() => stored("fep.role", "inspector") as Role);
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

  const label = t(health?.app_label ?? "Field Assistant");
  useEffect(() => {
    document.title = label;
  }, [label]);

  const value: Session = {
    name, role, health, label, industry,
    setIndustry: (i) => { setIndustryState(i); persist("fep.industry", i); },
    setName: (n) => { setNameState(n); persist("fep.name", n); },
    setRole: (r) => { setRoleState(r); persist("fep.role", r); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("SessionProvider missing");
  return s;
}
