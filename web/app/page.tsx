import { getServerSession } from "next-auth";
import Image from "next/image";
import { redirect } from "next/navigation";
import type { CSSProperties } from "react";
import { Suspense } from "react";

import { SignInButtons } from "@/components/auth/sign-in-buttons";
import { Logo } from "@/components/brand/logo";
import { AgentMark } from "@/components/team/agent-mark";
import { AGENTS, FOUR } from "@/components/team/agents";
import { authOptions, DEMO_ENABLED, GOOGLE_ENABLED } from "@/lib/auth";

const VIDEO = "https://youtu.be/n3XILic3pms";

const vars = (v: Record<string, string>) => v as CSSProperties;

const questions: Record<(typeof FOUR)[number], { a: string; how: string }> = {
  what: {
    a: "Every save is read, whatever the format: links, flyers, PDFs, voice notes, videos.",
    how: "Muse Spark reads it. When the read is thin, Muse Wonder digs for what it points to.",
  },
  true: {
    a: "Facts are checked against the official source, with the exact line quoted.",
    how: "Muse Wonder follows posts and blogs to the organisation's own page.",
  },
  for: {
    a: "Saves are grouped by the goals they serve, and the web is searched for more.",
    how: "Muse Wonder plans, searches and learns from every run.",
  },
  when: {
    a: "Each save gets a date or a moment, and comes back then with the next step.",
    how: "Code reads every date, in your time zone. No guessing.",
  },
};

/** A real run on the live demo: a blog post about a UN programme, followed to the source. */
const run: { agent: (typeof FOUR)[number]; code?: boolean; text: string }[] = [
  { agent: "what", text: "Read a blog post: a UN innovation programme “for young innovators”." },
  { agent: "true", text: "Opened the blog, then followed it to the programme's official site." },
  { agent: "true", code: true, text: "Refused a source: those words aren't on the page word for word." },
  { agent: "true", text: "Chose the official site. Found 3 things the post left out." },
  { agent: "true", text: "One question for you: do you live in one of the 7 states it covers?" },
  { agent: "when", code: true, text: "Brings it back Wed 11 Nov, from “open 1 September to 18 November 2026”." },
];

const numbers = [
  { n: "12/12", what: "real web pages judged right by code" },
  { n: "65/65", what: "quotes in answers found word for word" },
  { n: "30/30", what: "deadlines read right, in your time zone" },
  { n: "0", what: "tokens to watch a page that hasn't changed" },
];

const floating: { agent: (typeof FOUR)[number]; size: number; pos: string; style: Record<string, string> }[] = [
  { agent: "what", size: 64, pos: "left-[1%] top-[8%]", style: { "--dur": "6s", "--tilt": "-6deg" } },
  { agent: "true", size: 56, pos: "right-[6%] top-[12%]", style: { "--dur": "7s", "--delay": "-2s", "--tilt": "5deg" } },
  { agent: "for", size: 52, pos: "left-[9%] bottom-[12%]", style: { "--dur": "8s", "--delay": "-4s", "--tilt": "4deg" } },
  { agent: "when", size: 60, pos: "right-[10%] bottom-[16%]", style: { "--dur": "6.5s", "--delay": "-1s", "--tilt": "-5deg" } },
];

/** Signed-in visitors go straight to Today. Reading the session is request-time work. */
async function RedirectIfSignedIn() {
  const session = await getServerSession(authOptions);
  if (session?.user?.id) redirect("/today");
  return null;
}

export default function Home() {
  return (
    <main className="mx-auto max-w-6xl overflow-x-clip px-5 pb-24 pt-6">
      <Suspense fallback={null}>
        <RedirectIfSignedIn />
      </Suspense>
      <nav className="glass mx-auto flex max-w-3xl items-center justify-between rounded-full py-2.5 pl-5 pr-3">
        <Logo />
        <div className="flex items-center gap-1">
          <a href={VIDEO} className="hidden rounded-full px-4 py-2 text-sm font-semibold text-ink-2 hover:text-ink sm:block">
            Watch the demo
          </a>
          <a href="#how-it-works" className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
            How it works
          </a>
        </div>
      </nav>

      {/* Hero, with the four agents floating around it. */}
      <section className="relative py-20 text-center sm:py-28">
        <div
          className="drift pointer-events-none absolute left-1/2 top-1/2 -z-10 size-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgb(242_131_111/0.28),transparent_65%)]"
          aria-hidden
        />
        {floating.map(({ agent, size, pos, style }) => (
          <span key={agent} className={`float blink absolute hidden md:block ${pos}`} style={vars(style)} aria-hidden>
            <AgentMark agent={agent} size={size} />
          </span>
        ))}
        <a
          href={VIDEO}
          className="rise glass mx-auto inline-flex items-center gap-2 rounded-full py-1.5 pl-2 pr-4 text-sm font-semibold text-ink-2"
        >
          <Image src="/brand/muse.png" alt="" width={22} height={22} className="rounded-full" />
          Built on Meta&apos;s Muse models
          <span className="hidden text-red sm:inline">· Watch it work →</span>
        </a>
        <h1
          className="rise font-display mx-auto mt-6 max-w-4xl text-[40px] font-extrabold leading-[1.04] tracking-[-0.04em] sm:text-[64px]"
          style={vars({ "--delay": "0.1s" })}
        >
          Save anything.
          <br />
          It comes back <span className="text-red">when you need it.</span>
        </h1>
        <p className="rise mx-auto mt-5 max-w-xl text-lg leading-relaxed text-ink-2" style={vars({ "--delay": "0.2s" })}>
          Links, flyers, voice notes, videos. A team of agents reads every save, checks it against the
          source, and brings it back at the right moment.
        </p>
        <div className="rise" style={vars({ "--delay": "0.3s" })}>
          <SignInButtons demo={DEMO_ENABLED} google={GOOGLE_ENABLED} />
        </div>
      </section>

      {/* One save, coming back: the steps of a real run, on a loop. */}
      <section className="mx-auto grid max-w-5xl items-center gap-6 md:grid-cols-[1fr_1.4fr]">
        <div className="rise">
          <p className="text-sm font-semibold uppercase tracking-[0.12em] text-red">Watch one save</p>
          <h2 className="font-display mt-2 text-3xl font-extrabold tracking-[-0.03em] sm:text-4xl">
            The post said one thing. The source said another.
          </h2>
          <p className="mt-3 text-ink-2">
            A blog said a programme was for “young innovators”. Homing went to the official page and
            found the rule that decides if you can apply. Every line it shows is quoted from the source.
          </p>
          <div className="mt-5 flex justify-start">
            <div className="glass max-w-xs rounded-2xl rounded-bl-md px-4 py-3 text-left text-sm shadow-sm">
              <p className="font-semibold">You, to yourself</p>
              <p className="mt-1 text-ink-2">this one 👇 “UN innovation programme 2026/2027: apply now”</p>
            </div>
          </div>
        </div>
        <div className="glass rounded-[var(--radius-card)] p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between">
            <p className="font-display font-bold">Your agents</p>
            <span className="flex items-center gap-2 text-xs font-semibold text-ink-2">
              <span className="live-dot size-2 rounded-full bg-red" />
              Live run, replayed
            </span>
          </div>
          <ol className="space-y-2.5">
            {run.map(({ agent, code, text }, i) => (
              <li
                key={text}
                className="step flex items-start gap-3 rounded-2xl bg-white/70 px-3 py-2.5"
                style={vars({ "--delay": `${0.4 + i * 1.3}s` })}
              >
                <AgentMark agent={agent} size={22} />
                <div className="min-w-0 text-left text-sm">
                  <span className="font-semibold">{AGENTS[agent].label}</span>
                  {code && (
                    <span className="ml-2 rounded-full bg-grey-soft px-2 py-0.5 text-[11px] font-semibold text-ink-2">
                      Code
                    </span>
                  )}
                  <p className="text-ink-2">{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* The four agents. */}
      <section id="how-it-works" className="mt-24 scroll-mt-24">
        <h2 className="font-display text-center text-3xl font-extrabold tracking-[-0.03em] sm:text-4xl">
          Four questions. Every save.
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-ink-2">
          Models read, search and reason. Code checks every quote, number, date and rule before you see it.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {FOUR.map((agent, i) => (
            <div
              key={agent}
              className="rise lift glass group rounded-[var(--radius-card)] p-6"
              style={vars({ "--delay": `${i * 0.08}s` })}
            >
              <div className="flex items-center gap-3">
                <span className="blink transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-110" style={vars({ "--delay": `${i * 0.7}s` })}>
                  <AgentMark agent={agent} size={40} />
                </span>
                <h3 className="font-display text-lg font-bold tracking-[-0.02em]">{AGENTS[agent].label}</h3>
              </div>
              <p className="mt-3 text-ink-2">{questions[agent].a}</p>
              <p className="mt-3 border-t border-line pt-3 text-sm font-medium" style={{ color: AGENTS[agent].color }}>
                {questions[agent].how}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Proof. */}
      <section className="mt-20 grid grid-cols-2 gap-4 md:grid-cols-4">
        {numbers.map(({ n, what }) => (
          <div key={n + what} className="glass rounded-[var(--radius-card)] p-5 text-center">
            <p className="font-display text-4xl font-extrabold tracking-[-0.04em] text-red">{n}</p>
            <p className="mt-1 text-sm text-ink-2">{what}</p>
          </div>
        ))}
      </section>

      {/* Why, and the way in. */}
      <section className="mt-20 text-center">
        <p className="mx-auto max-w-2xl text-lg text-ink-2">
          People save out of fear of losing things. Folders don&apos;t bring them back. A save only frees your
          mind when you trust it will be there.
        </p>
        <h2 className="font-display mx-auto mt-6 max-w-2xl text-3xl font-extrabold tracking-[-0.03em] sm:text-5xl">
          Your saves, finally <span className="text-red">working for you.</span>
        </h2>
        <SignInButtons demo={DEMO_ENABLED} google={GOOGLE_ENABLED} />
        <p className="mt-10 text-sm">
          <a href={VIDEO} className="font-semibold text-ink-2 hover:text-ink">Watch the demo</a>
        </p>
      </section>
    </main>
  );
}
