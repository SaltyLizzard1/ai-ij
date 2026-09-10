"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const QUESTIONS = [
  {
    key: "yourMove",
    label: "Tell me about your move.",
    hint: "Where did you go, when, and what was happening in your life? Write like you're telling a friend — don't edit yourself.",
    placeholder: "I left [city] in [year] when...",
  },
  {
    key: "biggestFear",
    label: "What scared you most about leaving?",
    hint: "Be honest. The specific fears, not the general ones.",
    placeholder: "Honestly, what terrified me was...",
  },
  {
    key: "wisdomYouWish",
    label: "What do you wish someone had told you before you left?",
    hint: "The thing that would have made it less hard, or that you had to learn the painful way.",
    placeholder: "Nobody told me that...",
  },
  {
    key: "whoYouHelp",
    label: "Describe the person you want to help.",
    hint: "Not a demographic. What is their life like right now? What are they doing on a Sunday afternoon?",
    placeholder: "They're probably...",
  },
  {
    key: "theirFear",
    label: "What's the fear holding them back?",
    hint: "Go deeper than 'they're scared to leave.' What specifically are they afraid will happen?",
    placeholder: "They're terrified that if they go...",
  },
  {
    key: "theirDream",
    label: "What does their life look like when they finally do it?",
    hint: "Not the Instagram version. The real version that matters to them.",
    placeholder: "What they're really after is...",
  },
  {
    key: "yourTone",
    label: "How would you describe your natural tone?",
    hint: "Pick words that feel right: warm, direct, dry, funny, serious, tough-love, gentle, no-BS, poetic...",
    placeholder: "My natural tone is...",
  },
  {
    key: "phrasesYouUse",
    label: "List phrases or expressions you actually say.",
    hint: "Things you say out loud, things you text friends, things you think. Doesn't have to be eloquent.",
    placeholder: "Things I actually say: ...",
  },
  {
    key: "phrasesYouHate",
    label: "What words or phrases would you never use?",
    hint: "Things that make you cringe when you hear other coaches say them.",
    placeholder: "I would never say things like...",
  },
  {
    key: "yourWhy",
    label: "Why do you do this work?",
    hint: "Not the polished version. The real reason.",
    placeholder: "Honestly, I do this because...",
  },
];

export default function SetupPage() {
  const router = useRouter();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [current, setCurrent] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch("/api/profile")
      .then((r) => r.json())
      .then((p) => {
        if (p) setAnswers(p);
        setLoaded(true);
      });
  }, []);

  const q = QUESTIONS[current];
  const answer = answers[q.key] || "";
  const allAnswered = QUESTIONS.every((q) => (answers[q.key] || "").trim().length > 0);

  async function handleSave() {
    setSaving(true);
    await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(answers),
    });
    setSaving(false);
    router.push("/generate");
  }

  if (!loaded) return <div className="text-stone-400 text-sm">Loading...</div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-stone-900 mb-1">Voice Setup</h1>
        <p className="text-stone-500 text-sm">
          Question {current + 1} of {QUESTIONS.length}. Write freely — this is just for you and the AI.
        </p>
      </div>

      <div className="flex gap-1">
        {QUESTIONS.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            className={`h-1.5 rounded-full flex-1 transition-colors ${
              i === current ? "bg-stone-800" : answers[QUESTIONS[i].key] ? "bg-stone-300" : "bg-stone-100"
            }`}
          />
        ))}
      </div>

      <div className="bg-white rounded-xl border border-stone-200 p-8 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-stone-900 mb-1">{q.label}</h2>
          <p className="text-stone-400 text-sm">{q.hint}</p>
        </div>
        <textarea
          value={answer}
          onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })}
          placeholder={q.placeholder}
          rows={7}
          className="w-full rounded-lg border border-stone-200 px-4 py-3 text-stone-800 text-sm placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-stone-300 resize-none"
        />
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrent(current - 1)}
          disabled={current === 0}
          className="text-sm text-stone-400 hover:text-stone-700 disabled:opacity-30 transition-colors"
        >
          ← Back
        </button>

        <div className="flex gap-3">
          {current < QUESTIONS.length - 1 ? (
            <button
              onClick={() => setCurrent(current + 1)}
              disabled={!answer.trim()}
              className="px-5 py-2 bg-stone-800 text-white text-sm font-medium rounded-lg hover:bg-stone-700 disabled:opacity-30 transition-colors"
            >
              Next →
            </button>
          ) : (
            <button
              onClick={handleSave}
              disabled={!allAnswered || saving}
              className="px-5 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-30 transition-colors"
            >
              {saving ? "Saving..." : "Save my voice →"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
