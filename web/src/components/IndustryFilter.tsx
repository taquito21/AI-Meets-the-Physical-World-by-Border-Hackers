import { useSession } from "../session";

// One shared scenario filter (All / per industry), used by the asset list, dashboard and review queue.
export function IndustryFilter({ industries }: { industries: string[] }) {
  const { industry, setIndustry } = useSession();
  const options = ["All", ...industries.filter((i) => i !== "All").sort()];
  return (
    <div className="segmented" role="tablist" aria-label="Industry">
      {options.map((o) => (
        <button key={o} role="tab" aria-selected={industry === o} className={industry === o ? "on" : ""} onClick={() => setIndustry(o)}>
          {o === "All" ? "All industries" : o}
        </button>
      ))}
    </div>
  );
}
