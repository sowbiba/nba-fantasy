import Link from "next/link";

interface Props {
  todayDate: string;
  hasGamesTonight: boolean;
  hasPickToday: boolean;
}

export default function NoPickBanner({
  hasGamesTonight,
  hasPickToday,
}: Props) {
  if (!hasGamesTonight) return null;
  if (hasPickToday) return null;

  return (
    <Link
      href="#top-3"
      className="block mx-3 mt-3 rounded-[var(--radius-card)] border border-[color:var(--color-crimson)]/50 bg-gradient-to-r from-[color:var(--color-crimson)]/15 to-[color:var(--color-crimson)]/5 px-4 py-3 group relative overflow-hidden animate-pulse-red"
    >
      <span
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "linear-gradient(100deg, transparent 30%, rgba(255, 91, 91, 0.08) 50%, transparent 70%)",
          backgroundSize: "200% 100%",
          animation: "ttfl-shine 3s ease-in-out infinite",
        }}
      />
      <div className="relative flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-[color:var(--color-crimson)]/20 border border-[color:var(--color-crimson)]/50 flex items-center justify-center shrink-0">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-[color:var(--color-crimson)]"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--color-crimson)]">
            Pas encore pické
          </div>
          <div className="text-sm font-semibold text-[color:var(--color-text)] mt-0.5">
            Tu n&apos;as pas encore validé ton pick ce soir.
          </div>
        </div>
        <span className="text-[color:var(--color-crimson)] text-lg font-bold shrink-0 group-hover:translate-x-0.5 transition-transform">
          →
        </span>
      </div>
    </Link>
  );
}
