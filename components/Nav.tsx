"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Home" },
  { href: "/setup", label: "Voice Setup" },
  { href: "/generate", label: "Generate" },
  { href: "/calendar", label: "Calendar" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="border-b border-stone-200 bg-white px-6 py-4 flex items-center gap-8">
      <span className="font-semibold text-stone-800 text-lg tracking-tight">your voice</span>
      <div className="flex gap-6">
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`text-sm font-medium transition-colors ${
              path === l.href ? "text-stone-900" : "text-stone-400 hover:text-stone-700"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
