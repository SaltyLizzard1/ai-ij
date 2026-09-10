"use client";
import { useEffect, useState } from "react";

interface Draft {
  id: string;
  createdAt: string;
  angle: string;
  instagram: string;
  linkedin: string;
  tone: string;
  postedAt?: string;
  notes?: string;
}

export default function CalendarPage() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Record<string, "instagram" | "linkedin">>({});

  useEffect(() => {
    fetch("/api/drafts").then((r) => r.json()).then((d) => { setDrafts(d); setLoading(false); });
  }, []);

  async function markPosted(id: string) {
    const draft = drafts.find((d) => d.id === id);
    if (!draft) return;
    const updated = { ...draft, postedAt: new Date().toISOString() };
    await fetch("/api/drafts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updated) });
    setDrafts((prev) => prev.map((d) => (d.id === id ? updated : d)));
  }

  async function deleteDraft(id: string) {
    await fetch("/api/drafts", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
    setDrafts((prev) => prev.filter((d) => d.id !== id));
  }

  async function updateNotes(id: string, notes: string) {
    const draft = drafts.find((d) => d.id === id);
    if (!draft) return;
    const updated = { ...draft, notes };
    await fetch("/api/drafts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updated) });
    setDrafts((prev) => prev.map((d) => (d.id === id ? updated : d)));
  }

  const queued = drafts.filter((d) => !d.postedAt);
  const posted = drafts.filter((d) => d.postedAt);

  if (loading) return <div className="text-stone-400 text-sm">Loading...</div>;

  if (drafts.length === 0) {
    return <div className="text-center py-20"><p className="text-stone-400 text-sm">No drafts yet. Generate some posts first.</p></div>;
  }

  function DraftCard({ draft }: { draft: Draft }) {
    const tab = activeTab[draft.id] || "instagram";
    const date = new Date(draft.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const postedDate = draft.postedAt ? new Date(draft.postedAt).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : null;

    return (
      <div className={`bg-white rounded-xl border transition-all ${draft.postedAt ? "border-stone-100 opacity-70" : "border-stone-200"}`}>
        <button onClick={() => setExpanded(expanded === draft.id ? null : draft.id)} className="w-full text-left px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${draft.tone === "raw" ? "bg-red-50 text-red-600" : draft.tone === "practical" ? "bg-blue-50 text-blue-600" : "bg-amber-50 text-amber-600"}`}>{draft.tone}</span>
            <span className="text-sm font-medium text-stone-800">{draft.angle}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-stone-400">
            {postedDate ? <span>Posted {postedDate}</span> : <span>Saved {date}</span>}
            <span>{expanded === draft.id ? "↑" : "↓"}</span>
          </div>
        </button>

        {expanded === draft.id && (
          <div className="px-5 pb-5 space-y-4 border-t border-stone-100 pt-4">
            <div className="flex gap-2 text-xs">
              {(["instagram", "linkedin"] as const).map((p) => (
                <button key={p} onClick={() => setActiveTab((t) => ({ ...t, [draft.id]: p }))}
                  className={`px-3 py-1 rounded-full border transition-colors capitalize ${tab === p ? "bg-stone-800 text-white border-stone-800" : "border-stone-200 text-stone-500 hover:border-stone-400"}`}>
                  {p}
                </button>
              ))}
            </div>
            <p className="text-stone-700 text-sm leading-relaxed whitespace-pre-wrap">
              {tab === "instagram" ? draft.instagram : draft.linkedin}
            </p>
            <textarea
              defaultValue={draft.notes || ""}
              onBlur={(e) => updateNotes(draft.id, e.target.value)}
              placeholder="Notes to yourself..."
              rows={2}
              className="w-full text-xs text-stone-500 border border-stone-100 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-stone-200 resize-none bg-stone-50 placeholder:text-stone-300"
            />
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => navigator.clipboard.writeText(tab === "instagram" ? draft.instagram : draft.linkedin)}
                className="text-xs px-3 py-1.5 border border-stone-200 rounded-lg text-stone-600 hover:border-stone-400 transition-colors">
                Copy {tab}
              </button>
              {!draft.postedAt && (
                <button onClick={() => markPosted(draft.id)}
                  className="text-xs px-3 py-1.5 border border-emerald-200 rounded-lg text-emerald-700 hover:bg-emerald-50 transition-colors">
                  Mark as posted
                </button>
              )}
              <button onClick={() => deleteDraft(draft.id)}
                className="text-xs px-3 py-1.5 border border-red-100 rounded-lg text-red-400 hover:bg-red-50 transition-colors ml-auto">
                Delete
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-semibold text-stone-900">Content Calendar</h1>
      {queued.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-wider">Queue ({queued.length})</h2>
          {queued.map((d) => <DraftCard key={d.id} draft={d} />)}
        </section>
      )}
      {posted.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-wider">Posted ({posted.length})</h2>
          {posted.map((d) => <DraftCard key={d.id} draft={d} />)}
        </section>
      )}
    </div>
  );
}
