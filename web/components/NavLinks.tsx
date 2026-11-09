"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/demo", label: "Examples" },
  { href: "/catalog", label: "Tool catalog" },
];

export default function NavLinks() {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="flex gap-5 text-base">
      {LINKS.map((l) => {
        const on = path === l.href || path.startsWith(`${l.href}/`);
        return (
          <Link key={l.href} href={l.href} aria-current={on ? "page" : undefined}
            className={`py-2.5 ${on ? "text-ink font-semibold" : "text-muted"}`}>{l.label}</Link>
        );
      })}
    </nav>
  );
}
