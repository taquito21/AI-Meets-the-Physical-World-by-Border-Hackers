// Spanish dictionary, split by area. Keys are the exact English strings used in the code.
import app from "./es-app";
import server, { SERVER_PATTERNS } from "./es-server";

export const ES: Record<string, string> = { ...server, ...app };
export const ES_PATTERNS = SERVER_PATTERNS;
