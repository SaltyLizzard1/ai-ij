"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function Home() {
  const [hasProfile, setHasProfile] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/api/profile").then((r) => r.json()).then((p) => setHasProfile(!!p?.completedAt));
  }, []);

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-semibold text-stone-900 mb-3">Content that sounds like you.</h1>
        <p className="text-stone-500 text-lg leading-relaxed max-w-xl">
          For people who moved across the world and now help others do the same.
          Not AI copy. Not coach-speak. Your actual voice.
        </p>
      </div>

      <div className="grid gap-4">
        <Step
          number="1"
          title="Set up your voice"
          description="A one-time interview. Your answers train every post the app writes."
          href="/setup"
          done={hasProfile === true}
          cta={hasProfile ? "Edit your profile" : "Start here"}
        />
        <Step
          number="2"
          title="Generate posts"
          description="Pick an angle, add context if you want, get three tones for Instagram and LinkedIn."
          href="/generate"
          done={false}
          cta="Generate a post"
          locked={!hasProfile}
        />
        <Step
          number="3"
          title="Manage your calendar"
          description="Review drafts, schedule what you'll post, track what's done."
          href="/calendar"
          done={false}
          cta="View calendar"
          locked={!hasProfile}
        />
      </div>
    </div>
  );
}

function Step({
  number, title, description, href, done, cta, locked,
}: {
  number: string; title: string; description: string; href: string;
  done: boolean; cta: string; locked?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-6 flex items-start gap-5 ${locked ? "opacity-40" : "bg-white border-stone-200"}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold flex-shrink-0 mt-0.5 ${done ? "bg-emerald-100 text-emerald-700" : "bg-stone-100 text-stone-500"}`}>
        {done ? "✓" : number}
      </div>
      <div className="flex-1">
        <h2 className="font-semibold text-stone-800 mb-1">{title}</h2>
        <p className="text-stone-500 text-sm mb-4">{description}</p>
        {!locked && (
          <Link href={href} className="text-sm font-medium text-stone-700 hover:text-stone-900 underline underline-offset-4">
            {cta} →
          </Link>
        )}
      </div>
    </div>
  );
}
