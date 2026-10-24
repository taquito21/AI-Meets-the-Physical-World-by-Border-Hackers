// Login state: the Supabase session (in the browser) plus the user's profile from /api/me.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, type Me } from "./api";
import { supabase } from "./supabase";

interface Session {
  me: Me | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = async () => {
    try {
      setMe(await api.me());
      setError(null);
    } catch (e) {
      setMe(null);
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    let unsubscribe = () => undefined as void;
    supabase()
      .then(async (sb) => {
        const { data } = await sb.auth.getSession();
        if (data.session) await loadProfile();
        unsubscribe = sb.auth.onAuthStateChange((event) => {
          if (event === "SIGNED_OUT") setMe(null);
        }).data.subscription.unsubscribe;
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    return () => unsubscribe();
  }, []);

  const signOut = async () => {
    await (await supabase()).auth.signOut().catch(() => undefined);
    setMe(null);
  };
  setUnauthorizedHandler(() => void signOut());

  const signIn = async (email: string, password: string) => {
    const { error: err } = await (await supabase()).auth.signInWithPassword({ email: email.trim(), password });
    if (err) throw new Error(err.message === "Invalid login credentials" ? "Wrong email or password." : err.message);
    await loadProfile();
  };

  useEffect(() => {
    document.title = me ? `${me.company.name} · FieldSight` : "FieldSight";
  }, [me]);

  return <Ctx.Provider value={{ me, loading, error, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("SessionProvider missing");
  return s;
}
