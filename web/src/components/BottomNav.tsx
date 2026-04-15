"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "Ce soir", icon: "🏀" },
  { href: "/picks", label: "Mes picks", icon: "📋" },
  { href: "/strategy", label: "Stratégie", icon: "📊" },
  { href: "/injuries", label: "Blessés", icon: "🏥" },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-gray-950 border-t border-gray-800 z-50">
      <div className="flex max-w-lg mx-auto">
        {tabs.map((tab) => {
          const active = tab.href === "/"
            ? pathname === "/"
            : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex-1 flex flex-col items-center py-2.5 text-xs ${
                active
                  ? "text-blue-400 border-t-2 border-blue-400"
                  : "text-gray-500"
              }`}
            >
              <span className="text-lg">{tab.icon}</span>
              <span className="mt-0.5">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
