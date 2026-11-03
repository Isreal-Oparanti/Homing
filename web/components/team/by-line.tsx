import { Cpu, Sparkles } from "lucide-react";
import Image from "next/image";

/** muse-spark-1.3 -> Muse Spark: the names people know. */
export function modelName(model: string): string {
  if (model.startsWith("muse-voice-transcribe")) return "Muse Voice Transcribe";
  if (model.startsWith("muse-spark-open")) return "Muse Spark Open";
  if (model.startsWith("muse-spark")) return "Muse Spark";
  if (model.startsWith("muse-wonder")) return "Muse Wonder";
  if (model.startsWith("sam-")) return "SAM";
  return model;
}

/** The model's mark: Meta's Muse logo for the Muse models. */
export function ModelIcon({ name, size = 14 }: { name: string; size?: number }) {
  if (name.startsWith("Muse")) {
    return <Image src="/brand/muse.png" alt="" width={size} height={size} className="shrink-0" />;
  }
  return <Sparkles className="shrink-0" style={{ width: size, height: size }} aria-hidden />;
}

/**
 * Who did a step: the Meta models by name, or code. `models` may be ids or names;
 * an empty list means no model was used.
 */
export function ByLine({ models, how }: { models: string[]; how?: string }) {
  const names = [...new Set(models.map(modelName))];
  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted">
      {names.length ? (
        names.map((n) => (
          <span
            key={n}
            className="inline-flex items-center gap-1 rounded-full bg-grey-soft px-2 py-0.5 font-semibold text-ink-2"
          >
            <ModelIcon name={n} size={13} />
            {n}
          </span>
        ))
      ) : (
        <span className="inline-flex items-center gap-1 rounded-full bg-grey-soft px-2 py-0.5 font-semibold text-ink-2">
          <Cpu className="size-3" aria-hidden />
          Code
        </span>
      )}
      {how && <span>{how}</span>}
    </p>
  );
}
