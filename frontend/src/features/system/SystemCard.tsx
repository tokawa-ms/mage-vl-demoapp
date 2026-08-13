import type { ReactNode } from "react";

interface Props {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: "green" | "amber" | "cyan" | "violet" | "neutral";
}

export function SystemCard({ icon, label, value, detail, tone }: Props) {
  return (
    <article className={`system-card tone-${tone}`}>
      <div className="system-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}
