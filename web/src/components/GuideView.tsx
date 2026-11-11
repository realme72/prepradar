import { useMemo, type ComponentProps } from "react";
import Markdown from "react-markdown";

type Props = { markdown: string };

// The guide cites questions as [Q12] and write-ups as [S3]. Turn those into links:
//   [Q12] -> jumps to its entry under "Cited questions" (hover shows the text)
//   [S3]  -> opens the candidate's write-up
function linkCitations(md: string) {
  const sources: Record<string, string> = {};
  for (const m of md.matchAll(/^- \[(S\d+)\] (\S+)$/gm)) sources[m[1]] = m[2];

  const questions: Record<string, string> = {};
  const cited = md.split("## Cited questions")[1]?.split("\n## ")[0] ?? "";
  for (const m of cited.matchAll(/^- \*\*\[(Q\d+)\]\*\* (.+?) — /gm)) questions[m[1]] = m[2];

  // Only entries in the "Cited questions" index become anchor targets ("#def-Q12"
  // renders as <strong id="Q12">); the same **[Q12]** in a section stays a link.
  const [head, tail = ""] = md.split("## Cited questions");
  const index = tail.replace(/^- \*\*\[(Q\d+)\]\*\*/gm, (_, id) => `- [${id}](#def-${id})`);
  const linked = (tail ? `${head}## Cited questions${index}` : head)
    // every other [Q12] / [S3] becomes a link (the lookahead skips ones already linked)
    .replace(/\[(Q\d+)\](?!\()/g, (_, id) => `[${id}](#${id})`)
    .replace(/\[(S\d+)\](?!\()/g, (whole, id) => (sources[id] ? `[${id}](${sources[id]})` : whole));
  return { linked, questions };
}

// Builds the <a> replacement. It's created once per guide (in useMemo below), not
// inside the render body: a component defined during render is a new type every
// time, and React would unmount and remount every link on each re-render.
function makeLink(questions: Record<string, string>) {
  return function Link({ href = "", children }: ComponentProps<"a">) {
    if (href.startsWith("#def-")) {
      return <strong id={href.slice(5)} className="cite-target">{children}</strong>;
    }
    if (href.startsWith("#Q")) {
      return <a href={href} className="cite" title={questions[href.slice(1)]}>{children}</a>;
    }
    const source = /^S\d+$/.test(String(children));
    return (
      <a href={href} className={source ? "cite" : undefined} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  };
}

export function GuideView({ markdown }: Props) {
  const { linked, components } = useMemo(() => {
    const { linked, questions } = linkCitations(markdown);
    // react-markdown turns markdown into React elements. The `components` prop
    // swaps in our own component for any tag it would render; here, every <a>.
    return { linked, components: { a: makeLink(questions) } };
  }, [markdown]);

  return (
    <article className="guide">
      <Markdown components={components}>{linked}</Markdown>
    </article>
  );
}
