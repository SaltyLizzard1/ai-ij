import { NextRequest, NextResponse } from "next/server";
import { getProfile, saveProfile } from "@/lib/storage";

export async function GET() {
  const profile = getProfile();
  return NextResponse.json(profile);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  saveProfile({ ...body, completedAt: new Date().toISOString() });
  return NextResponse.json({ ok: true });
}
