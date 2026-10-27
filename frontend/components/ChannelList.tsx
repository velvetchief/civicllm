import { safeHref } from "@/lib/markdownLite";
import { channelToStep } from "@/lib/types";
import type { Channel, Lang } from "@/lib/types";

// Tenant handoff channels (bilingual objects, localized at render time via
// channelToStep). Rendered on error dead-ends and refusals so every failure
// still routes the resident somewhere real. Distinct from Answer.next_steps,
// which arrive already localized from the API and keep their own rendering
// in AnswerView.

export function ChannelList({
  channels,
  lang,
  heading,
  prominent,
}: {
  channels: Channel[];
  lang: Lang;
  heading: string;
  prominent?: boolean;
}) {
  if (channels.length === 0) return null;
  return (
    <section
      className={prominent ? "steps prominent" : "steps"}
      aria-label={heading}
    >
      <h3>{heading}</h3>
      <ul>
        {channels.map((c, i) => {
          const step = channelToStep(c, lang);
          const href = safeHref(step.url);
          return (
            <li key={i}>
              {href ? (
                <a href={href} target="_blank" rel="noreferrer">
                  <b>{step.label}</b>
                </a>
              ) : (
                <b>{step.label}</b>
              )}
              {step.detail && <span className="step-detail">{step.detail}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
