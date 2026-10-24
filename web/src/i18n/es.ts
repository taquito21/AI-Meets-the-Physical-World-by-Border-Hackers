// Spanish dictionary, split by area. Keys are the exact English strings used in the code.
import auth from "./es-auth";
import common from "./es-common";
import face from "./es-face";
import inspection from "./es-inspection";
import pages from "./es-pages";
import review from "./es-review";
import server, { SERVER_PATTERNS } from "./es-server";

export const ES: Record<string, string> = { ...server, ...pages, ...review, ...inspection, ...face, ...auth, ...common };
export const ES_PATTERNS = SERVER_PATTERNS;
