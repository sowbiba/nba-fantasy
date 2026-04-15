export function ProsBlock({ pros }: { pros: string[] }) {
  return (
    <div className="relative overflow-hidden rounded-[var(--radius-card)] border border-[color:var(--color-emerald)]/25 bg-[color:var(--color-emerald)]/[0.05] p-4">
      <div className="absolute top-0 left-0 h-full w-[3px] bg-[color:var(--color-emerald)]" />
      <div className="flex items-center gap-2 mb-2">
        <span className="font-display text-sm tracking-[0.25em] text-[color:var(--color-emerald)]">
          POUR
        </span>
        <span className="h-px flex-1 bg-[color:var(--color-emerald)]/20" />
      </div>
      <ul className="space-y-1.5 text-sm text-[color:var(--color-text-soft)] leading-relaxed">
        {pros.map((p, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-[color:var(--color-emerald)] mt-[2px]">+</span>
            <span>{p}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ConsBlock({ cons }: { cons: string[] }) {
  return (
    <div className="relative overflow-hidden rounded-[var(--radius-card)] border border-[color:var(--color-crimson)]/25 bg-[color:var(--color-crimson)]/[0.05] p-4">
      <div className="absolute top-0 left-0 h-full w-[3px] bg-[color:var(--color-crimson)]" />
      <div className="flex items-center gap-2 mb-2">
        <span className="font-display text-sm tracking-[0.25em] text-[color:var(--color-crimson)]">
          CONTRE
        </span>
        <span className="h-px flex-1 bg-[color:var(--color-crimson)]/20" />
      </div>
      <ul className="space-y-1.5 text-sm text-[color:var(--color-text-soft)] leading-relaxed">
        {cons.map((c, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-[color:var(--color-crimson)] mt-[2px]">−</span>
            <span>{c}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function VerdictBlock({ verdict }: { verdict: string }) {
  return (
    <div className="relative overflow-hidden rounded-[var(--radius-card)] border border-[color:var(--color-gold)]/35 bg-gradient-to-br from-[color:var(--color-gold)]/[0.08] to-[color:var(--color-flame)]/[0.04] p-4">
      <div className="absolute top-0 left-0 h-full w-[3px] bg-gradient-to-b from-[color:var(--color-gold)] to-[color:var(--color-flame)]" />
      <div className="flex items-center gap-2 mb-2">
        <span className="font-display text-sm tracking-[0.25em] gold-text">
          VERDICT
        </span>
        <span className="h-px flex-1 bg-[color:var(--color-gold)]/25" />
      </div>
      <p className="text-sm text-[color:var(--color-text)] leading-relaxed">
        {verdict}
      </p>
    </div>
  );
}
