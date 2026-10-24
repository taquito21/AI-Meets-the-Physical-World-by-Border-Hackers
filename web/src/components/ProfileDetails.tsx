// Inspection-profile details for one requirement. Every field is optional, so assets with a simple
// profile (furniture) and a rich one (electrical) render through the same component.
interface Props {
  req: {
    inspection_points?: string[]; acceptance_criteria?: string[]; possible_findings?: string[];
    risks?: string[]; recommended_actions?: string[]; human_review_required?: boolean;
  };
}

const List = ({ title, items, className }: { title: string; items?: string[]; className?: string }) =>
  items && items.length ? (<><h4>{title}</h4><ul className={className}>{items.map((x) => <li key={x}>{x}</li>)}</ul></>) : null;

export function ProfileDetails({ req }: Props) {
  return (
    <>
      <List title="Inspection points" items={req.inspection_points} />
      <List title="Acceptance criteria (manufacturer)" items={req.acceptance_criteria} />
      <List title="Possible findings" items={req.possible_findings} />
      <List title="Risks" items={req.risks} className="flag" />
      <List title="Recommended actions" items={req.recommended_actions} />
      {req.human_review_required && (
        <p className="small"><span className="chip chip-amber">Human review required</span> A qualified person must review this evidence; AI output is advisory.</p>
      )}
    </>
  );
}
