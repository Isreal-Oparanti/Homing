import { Logo } from "@/components/brand/logo";

const questions = [
  { q: "What is it?", a: "Every save is read, whatever the format: links, flyers, PDFs, voice notes, videos." },
  { q: "Is it true?", a: "Facts are checked against the official source, with the exact line quoted." },
  { q: "What's it for?", a: "Saves are grouped by the goals they serve, so nothing sits alone." },
  { q: "When will you need it?", a: "Each save gets a date or moment, and comes back then with the next step." },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-6xl px-5 pb-24 pt-6">
      <nav className="glass mx-auto flex max-w-3xl items-center justify-between rounded-full py-2.5 pl-5 pr-3">
        <Logo />
        <a
          href="#how-it-works"
          className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white"
        >
          How it works
        </a>
      </nav>

      <section className="py-20 text-center sm:py-28">
        <h1 className="font-display mx-auto max-w-4xl text-[40px] font-extrabold leading-[1.04] tracking-[-0.04em] sm:text-[64px]">
          Save anything.
          <br />
          It comes back <span className="text-red">when you need it.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-ink-2">
          Links, flyers, voice notes, videos. Homing reads every save, checks it against the source,
          and brings it back at the right moment.
        </p>
        <a
          href="#how-it-works"
          className="mt-8 inline-block rounded-full bg-red px-6 py-3 text-sm font-semibold text-white shadow-[0_6px_20px_rgb(210_64_47/0.35)] hover:bg-red-600"
        >
          See how it works
        </a>
      </section>

      <section id="how-it-works" className="grid gap-4 sm:grid-cols-2">
        {questions.map(({ q, a }) => (
          <div key={q} className="glass rounded-[var(--radius-card)] p-6">
            <h2 className="font-display text-lg font-bold tracking-[-0.02em]">{q}</h2>
            <p className="mt-2 text-ink-2">{a}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
