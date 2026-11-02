import { useLayoutEffect, useRef, useState } from "react";

const URL_PATTERN = /(https?:\/\/[^\s<>"]*[^\s<>".,;:!?)])/;

function Linked({ text }: { text: string }) {
  return text.split(URL_PATTERN).map((part, index) =>
    index % 2 === 1 ? (
      <a key={index} href={part} target="_blank" rel="noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  );
}

type Props = { text: string; source: string | null };

export function Rules({ text, source }: Props) {
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  const extraSource = source && !text.includes(source) ? source : null;

  useLayoutEffect(() => {
    const element = body.current;
    if (element) setOverflows(element.scrollHeight > element.clientHeight + 1);
  }, [text]);

  if (!text && !extraSource) return null;

  return (
    <section className="rules">
      <div className="rules-head">
        <span>Rules</span>
        {(overflows || open) && (
          <button onClick={() => setOpen(!open)}>{open ? "Show less" : "Show full rules"}</button>
        )}
      </div>
      <div ref={body} className={`rules-text ${open ? "" : "clamped"}`}>
        <Linked text={text} />
        {extraSource && (
          <>
            {"\n\nSource: "}
            <Linked text={extraSource} />
          </>
        )}
      </div>
    </section>
  );
}
