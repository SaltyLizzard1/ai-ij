import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");

function ensureDir() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
}

export interface VoiceProfile {
  completedAt?: string;
  yourMove: string;
  biggestFear: string;
  wisdomYouWish: string;
  whoYouHelp: string;
  theirFear: string;
  theirDream: string;
  yourTone: string;
  phrasesYouUse: string;
  phrasesYouHate: string;
  yourWhy: string;
}

export interface Draft {
  id: string;
  createdAt: string;
  angle: string;
  instagram: string;
  linkedin: string;
  tone: "raw" | "practical" | "reflective";
  scheduledFor?: string;
  postedAt?: string;
  platform?: "instagram" | "linkedin" | "both";
  notes?: string;
}

const PROFILE_FILE = path.join(DATA_DIR, "profile.json");
const DRAFTS_FILE = path.join(DATA_DIR, "drafts.json");

export function getProfile(): VoiceProfile | null {
  ensureDir();
  if (!fs.existsSync(PROFILE_FILE)) return null;
  return JSON.parse(fs.readFileSync(PROFILE_FILE, "utf-8"));
}

export function saveProfile(profile: VoiceProfile): void {
  ensureDir();
  fs.writeFileSync(PROFILE_FILE, JSON.stringify(profile, null, 2));
}

export function getDrafts(): Draft[] {
  ensureDir();
  if (!fs.existsSync(DRAFTS_FILE)) return [];
  return JSON.parse(fs.readFileSync(DRAFTS_FILE, "utf-8"));
}

export function saveDraft(draft: Draft): void {
  ensureDir();
  const drafts = getDrafts();
  const idx = drafts.findIndex((d) => d.id === draft.id);
  if (idx >= 0) drafts[idx] = draft;
  else drafts.unshift(draft);
  fs.writeFileSync(DRAFTS_FILE, JSON.stringify(drafts, null, 2));
}

export function deleteDraft(id: string): void {
  ensureDir();
  const drafts = getDrafts().filter((d) => d.id !== id);
  fs.writeFileSync(DRAFTS_FILE, JSON.stringify(drafts, null, 2));
}
