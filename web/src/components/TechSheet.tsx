import type { Component } from "../api";
import { t } from "../i18n";

// Structured technical sheet for any component. Demonstration values are always marked as such.
export function TechSheet({ comp }: { comp: Component }) {
  const hasDemo = comp.specs?.some((s) => s.demo_value);
  return (
    <div className="techsheet">
      <dl className="kv">
        <dt>{t("Component")}</dt><dd>{comp.name}</dd>
        <dt>{t("Component ID")}</dt><dd><code>{comp.id}</code></dd>
        {comp.category && <><dt>{t("Category")}</dt><dd>{comp.category}</dd></>}
        <dt>{t("Part number")}</dt><dd>{comp.part_number}</dd>
        <dt>{t("Quantity")}</dt><dd>{comp.quantity}</dd>
        {comp.material && <><dt>{t("Material")}</dt><dd>{comp.material}</dd></>}
        {comp.inspection_type && <><dt>{t("Inspection type")}</dt><dd>{comp.inspection_type}</dd></>}
        {comp.specs?.map((s) => (
          <span key={s.label} style={{ display: "contents" }}>
            <dt>{s.label}</dt><dd>{s.value}{s.demo_value && <sup className="demo-mark" title={t("Demonstration value, not from a real datasheet")}>{t("demo")}</sup>}</dd>
          </span>
        ))}
      </dl>
      {hasDemo && <p className="tiny muted">{t("Values marked \"demo\" are fictional demonstration data, not from a manufacturer datasheet.")}</p>}
    </div>
  );
}
