"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Tab = {
  href: string;
  label: string;
  icon: React.ReactNode;
};

const IconBall = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="w-[22px] h-[22px]"
  >
    <circle cx="12" cy="12" r="10" />
    <path d="M4.93 4.93c4.97 4.97 9.19 9.19 14.14 14.14" />
    <path d="M19.07 4.93c-4.97 4.97-9.19 9.19-14.14 14.14" />
    <path d="M2 12h20" />
  </svg>
);

const IconList = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="w-[22px] h-[22px]"
  >
    <path d="M8 6h13" />
    <path d="M8 12h13" />
    <path d="M8 18h13" />
    <circle cx="4" cy="6" r="1" />
    <circle cx="4" cy="12" r="1" />
    <circle cx="4" cy="18" r="1" />
  </svg>
);

const IconChart = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="w-[22px] h-[22px]"
  >
    <path d="M3 3v18h18" />
    <path d="M7 14l4-4 4 4 5-5" />
  </svg>
);

const IconMed = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="w-[22px] h-[22px]"
  >
    <path d="M4.5 12.5 12 5l7.5 7.5" />
    <path d="M5 11v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8" />
    <path d="M10 21v-5a2 2 0 0 1 4 0v5" />
  </svg>
);

const tabs: Tab[] = [
  { href: "/", label: "Ce soir", icon: IconBall },
  { href: "/picks", label: "Picks", icon: IconList },
  { href: "/strategy", label: "Stratégie", icon: IconChart },
  { href: "/injuries", label: "Blessés", icon: IconMed },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 backdrop-blur-xl bg-[color:var(--color-ink)]/80 border-t border-white/[0.06]"
      style={{
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
      }}
    >
      <div className="flex max-w-lg mx-auto relative">
        {/* top highlight line */}
        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-[color:var(--color-flame)]/40 to-transparent" />
        {tabs.map((tab) => {
          const active =
            tab.href === "/"
              ? pathname === "/"
              : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex-1 flex flex-col items-center gap-1 py-2.5 relative transition-colors ${
                active
                  ? "text-[color:var(--color-flame)]"
                  : "text-[color:var(--color-text-mute)] hover:text-[color:var(--color-text-soft)]"
              }`}
            >
              {active && (
                <span className="absolute top-0 left-1/2 -translate-x-1/2 h-[3px] w-10 rounded-full bg-[color:var(--color-flame)] shadow-[0_0_12px_rgba(255,91,31,0.6)]" />
              )}
              <span
                className={`transition-transform ${
                  active ? "scale-110" : "scale-100"
                }`}
              >
                {tab.icon}
              </span>
              <span
                className={`text-[10px] tracking-[0.12em] uppercase font-semibold ${
                  active ? "text-[color:var(--color-flame)]" : ""
                }`}
              >
                {tab.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
