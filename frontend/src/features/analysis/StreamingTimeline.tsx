import { CheckCircle2, CircleOff, Clock3 } from "lucide-react";
import type { StreamEvent } from "../../types/api";

export function StreamingTimeline({ events }: { events: StreamEvent[] }) {
  return (
    <section className="timeline-section" aria-labelledby="timeline-title">
      <div className="result-section-title"><Clock3 size={15} /><h3 id="timeline-title">Streaming timeline</h3><span>{events.length} segments</span></div>
      <div className="timeline">
        {events.map((event, index) => {
          const probability = Math.max(0, Math.min(1, Number(event.probability)));
          const accepted = /accept|pass|yes|emit|answer/i.test(event.decision);
          return (
            <article className="timeline-row" key={`${event.timestamp}-${index}`}>
              <time>{formatTimestamp(event.timestamp)}</time>
              <div className="probability">
                <div><span style={{ width: `${probability * 100}%` }} /></div>
                <strong>{Math.round(probability * 100)}%</strong>
              </div>
              <span className={`decision ${accepted ? "accepted" : "skipped"}`}>
                {accepted ? <CheckCircle2 size={13} /> : <CircleOff size={13} />}{event.decision}
              </span>
              <p>{event.text || "No response emitted for this segment."}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function formatTimestamp(value: number | string) {
  if (typeof value === "string" && value.includes(":")) return value;
  const total = Number(value) || 0;
  const minutes = Math.floor(total / 60);
  return `${minutes.toString().padStart(2, "0")}:${Math.floor(total % 60).toString().padStart(2, "0")}`;
}
