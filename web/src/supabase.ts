// Supabase is used in the browser for login only; all data goes through the backend API.
// The URL and publishable key come from the backend (/api/config), so one build works against any server.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: Promise<SupabaseClient> | null = null;

export function supabase(): Promise<SupabaseClient> {
  if (!client) {
    client = fetch("/api/config")
      .then((r) => r.json())
      .then((c) => {
        if (!c.supabase_url || !c.supabase_publishable_key) {
          throw new Error("Login is not configured on the server (SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY).");
        }
        return createClient(c.supabase_url, c.supabase_publishable_key);
      })
      .catch((e) => {
        client = null; // allow a retry once the server is reachable
        throw e;
      });
  }
  return client;
}

// Current access token; supabase-js refreshes it automatically before it expires.
export async function accessToken(): Promise<string | null> {
  const { data } = await (await supabase()).auth.getSession();
  return data.session?.access_token ?? null;
}
