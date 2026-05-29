import { NextResponse } from "next/server";
import { promises as fs } from "fs";

type BackendEvent = {
  id: number;
  device_id: string;
  raw_event: string;
  predicted_label: string | null;
  confidence: number | null;
  server_received_at: string;
};

type NewsArticle = {
  title?: string;
  publishedAt?: string;
  source?: {
    name?: string;
  };
};

type Summary = {
  total: number;
  inCount: number;
  outCount: number;
  personInCount: number;
  personOutCount: number;
  commonInHour: string | null;
  commonOutHour: string | null;
  recent: BackendEvent[];
};

const GEMINI_MODEL = "gemini-2.5-flash";
const INSIGHTS_CACHE_PATH = "/tmp/time-sense-insights-cache.json";

type InsightCache = {
  date: string;
  text: string;
  updatedAt: string;
};

function normalizeLabel(event: BackendEvent): string {
  return (event.predicted_label ?? event.raw_event ?? "").toUpperCase();
}

function classifyEvent(event: BackendEvent) {
  const label = normalizeLabel(event);
  const isPersonIn = label.includes("ORANG_MASUK");
  const isPersonOut = label.includes("ORANG_KELUAR");

  let kind: "IN" | "OUT" | "UNKNOWN" = "UNKNOWN";
  if (label.includes("PULANG") || label.includes("MASUK") || label === "S2_S1") kind = "IN";
  if (label.includes("PERGI") || label.includes("KELUAR") || label === "S1_S2") kind = "OUT";

  return { kind, isPersonIn, isPersonOut };
}

function modeHour(hours: number[]): string | null {
  if (hours.length === 0) return null;
  const counts = new Map<number, number>();
  for (const h of hours) counts.set(h, (counts.get(h) ?? 0) + 1);
  let bestHour: number | null = null;
  let bestCount = -1;
  for (const [hour, count] of counts.entries()) {
    if (count > bestCount || (count === bestCount && (bestHour === null || hour < bestHour))) {
      bestHour = hour;
      bestCount = count;
    }
  }
  if (bestHour === null) return null;
  return `${String(bestHour).padStart(2, "0")}:00`;
}

function buildSummary(events: BackendEvent[]): Summary {
  const sorted = [...events].sort((a, b) => {
    const ta = new Date(a.server_received_at).getTime();
    const tb = new Date(b.server_received_at).getTime();
    return (isNaN(tb) ? 0 : tb) - (isNaN(ta) ? 0 : ta);
  });
  const recent = sorted.slice(0, 20);

  let inCount = 0;
  let outCount = 0;
  let personInCount = 0;
  let personOutCount = 0;
  const inHours: number[] = [];
  const outHours: number[] = [];

  for (const event of events) {
    const { kind, isPersonIn, isPersonOut } = classifyEvent(event);
    if (kind === "IN") inCount += 1;
    if (kind === "OUT") outCount += 1;
    if (isPersonIn) personInCount += 1;
    if (isPersonOut) personOutCount += 1;

    const time = new Date(event.server_received_at);
    if (!isNaN(time.getTime())) {
      if (kind === "IN") inHours.push(time.getHours());
      if (kind === "OUT") outHours.push(time.getHours());
    }
  }

  return {
    total: events.length,
    inCount,
    outCount,
    personInCount,
    personOutCount,
    commonInHour: modeHour(inHours),
    commonOutHour: modeHour(outHours),
    recent,
  };
}

function formatEventLine(event: BackendEvent): string {
  const label = event.predicted_label ?? event.raw_event ?? "UNKNOWN";
  return `${event.server_received_at} | ${label}`;
}

function formatNewsLine(article: NewsArticle): string {
  const title = article.title ?? "(judul tidak tersedia)";
  const source = article.source?.name ? ` - ${article.source.name}` : "";
  const published = article.publishedAt ? ` (${article.publishedAt})` : "";
  return `${title}${source}${published}`;
}

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function pickOpeningHints(seed: number): string {
  const options = [
    "Akhir-akhir ini",
    "Beberapa hari ini",
    "Dalam pekan ini",
    "Belakangan ini",
    "Sepekan terakhir",
    "Dalam beberapa hari terakhir",
  ];
  const start = seed % options.length;
  const rotated = options.slice(start).concat(options.slice(0, start));
  return rotated.slice(0, 3).join(", ");
}

function pickStyleHint(seed: number): string {
  const styles = [
    "Gaya hangat dan suportif, gunakan variasi kosakata dan kalimat ajakan.",
    "Gaya reflektif, ajak evaluasi singkat tanpa menggurui.",
    "Gaya praktis, fokus pada saran yang bisa langsung dilakukan.",
    "Gaya apresiatif, soroti satu kemajuan kecil lalu beri saran lanjutan.",
    "Gaya waspada namun tenang untuk aspek keamanan.",
  ];
  return styles[seed % styles.length];
}

function buildPrompt(
  summary: Summary,
  newsLines: string[],
  styleSeed: number,
  historyError?: string | null,
  newsError?: string | null,
) {
  const recentLines = summary.recent.map(formatEventLine).join("\n");
  const newsBlock = newsLines.length > 0 ? newsLines.join("\n") : "(tidak ada data berita)";
  const openingHints = pickOpeningHints(styleSeed);
  const styleHint = pickStyleHint(styleSeed);

  return `Kamu adalah asisten ringkas dan faktual. Tulis tepat 3 poin dalam bahasa Indonesia.
Setiap poin 2-3 kalimat, minimal 20 kata per poin. Jangan gunakan penomoran atau bullet, cukup pisahkan dengan baris baru.
Hindari pembuka generik seperti "Berdasarkan data" atau "Dari data". Mulai tiap poin dengan kalimat yang spesifik dan mudah dipahami.
Variasikan pembuka seperti: ${openingHints}. Jangan ulangi pembuka yang sama di semua poin.
${styleHint} Hindari memulai poin dengan "Aktivitas keluar/pergi".

Gunakan data ini (jangan mengarang di luar input):
- Total event: ${summary.total}
- Masuk/Pulang: ${summary.inCount}
- Keluar/Pergi: ${summary.outCount}
- Orang masuk: ${summary.personInCount}
- Orang keluar: ${summary.personOutCount}
- Jam masuk terbanyak: ${summary.commonInHour ?? "tidak cukup data"}
- Jam keluar terbanyak: ${summary.commonOutHour ?? "tidak cukup data"}
${historyError ? `- Catatan history: ${historyError}` : ""}

Riwayat terbaru (maks 20):
${recentLines || "(tidak ada data riwayat)"}

Berita Indonesia terbaru (pilih 1, tanpa URL):
${newsBlock}
${newsError ? `Catatan berita: ${newsError}` : ""}

Tugas:
1) Jelaskan kebiasaan pulang/pergi berdasarkan data.
2) Sebutkan jumlah orang masuk/keluar jika ada.
3) Beri saran waktu (misal jam berangkat/pulang).
4) Sisipkan 1-2 berita dari daftar sebagai konteks.
5) Jika ada berita bertema kriminalitas/keamanan, tambahkan saran kewaspadaan tanpa melebih-lebihkan.
Jika data kosong, tetap buat 3 poin berisi saran umum singkat (kesehatan, keamanan, rutinitas).`;
}

function splitLines(text: string): string[] {
  return text
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function buildFallbackLines(summary: Summary, newsLines: string[], seed: number): string[] {
  const newsTitle = newsLines[0]?.replace(/\s*\(.*\)$/, "") ?? "berita terbaru hari ini";
  const newsTitle2 = newsLines[1]?.replace(/\s*\(.*\)$/, "") ?? null;
  const inHour = summary.commonInHour ? `sekitar jam ${summary.commonInHour}` : "di jam yang konsisten";
  const outHour = summary.commonOutHour ? `sekitar jam ${summary.commonOutHour}` : "di jam yang konsisten";
  const newsContext = newsTitle2 ? `"${newsTitle}" dan "${newsTitle2}"` : `"${newsTitle}"`;
  const variants: string[][] = [
    [
      `Belakangan ini ada ${summary.total} aktivitas dengan pola masuk/pulang yang cukup konsisten ${inHour}. Ritme yang stabil membantu pemulihan, jadi jaga waktu istirahat agar tidak terlalu bergeser dari kebiasaan.`,
      `Ada ${summary.personInCount} orang masuk dan ${summary.personOutCount} orang keluar. Demi keamanan, pastikan pintu terkunci rapat terutama saat kamu ${outHour}, serta nyalakan lampu luar bila rumah kosong.`,
      `Sebagai konteks, ada berita ${newsContext}. Atur waktu berangkat dan pulang agar tetap aman sekaligus efisien sepanjang hari.`,
    ],
    [
      `Dalam beberapa hari terakhir tercatat ${summary.total} aktivitas, dan jam masuk/pulang kamu sering muncul ${inHour}. Pola ini bagus jika disertai tidur cukup, jadi usahakan tidak menunda waktu pulang terlalu malam.`,
      `Soal keamanan, terdeteksi ${summary.personInCount} orang masuk dan ${summary.personOutCount} orang keluar. Kunci pintu dengan benar terutama saat kamu ${outHour}, dan periksa kembali sebelum tidur.`,
      `Konteks berita hari ini menyebut ${newsContext}. Gunakan informasi ini untuk menyesuaikan jam keluar agar lebih aman dan terukur.`,
    ],
    [
      `Akhir-akhir ini aktivitas total mencapai ${summary.total}, dengan jam masuk/pulang yang terlihat ${inHour}. Menjaga konsistensi jam pulang akan membantu energi tetap stabil dan fokus di hari berikutnya.`,
      `Untuk keamanan, ada ${summary.personInCount} orang masuk dan ${summary.personOutCount} orang keluar. Pastikan pintu dan akses utama terkunci rapat saat kamu ${outHour}, apalagi jika rumah kosong.`,
      `Sebagai latar, berita ${newsContext} bisa jadi pengingat untuk lebih waspada. Pertimbangkan membatasi keluar malam jika tidak mendesak.`,
    ],
  ];

  return variants[seed % variants.length];
}

function isSafetyNews(newsLines: string[]): boolean {
  const keywords = [
    "pencurian",
    "perampokan",
    "begal",
    "penyerangan",
    "kriminal",
    "kejahatan",
    "pembobolan",
    "perampas",
    "kekerasan",
  ];
  return newsLines.some((line) => {
    const lower = line.toLowerCase();
    return keywords.some((k) => lower.includes(k));
  });
}

function normalizeInsightText(raw: string, summary: Summary, newsLines: string[], seed: number): string {
  let lines = splitLines(raw);

  if (lines.length < 3) {
    const sentences = splitSentences(raw);
    lines = sentences.length >= 3 ? sentences : lines;
  }

  const fallback = buildFallbackLines(summary, newsLines, seed);

  const cleaned: string[] = [];
  for (const line of lines) {
    const lower = line.toLowerCase();
    if (lower.startsWith("berdasarkan data") || lower.startsWith("dari data")) {
      continue;
    }
    if (lower.startsWith("aktivitas keluar/pergi")) {
      continue;
    }
    if (lower.startsWith("aktivitas keluar")) {
      continue;
    }
    cleaned.push(line);
  }

  lines = cleaned.length > 0 ? cleaned : lines;

  if (lines.length < 3) {
    const merged = [...lines, ...fallback];
    lines = merged.slice(0, 3);
  }

  if (lines.length > 3) {
    lines = lines.slice(0, 3);
  }

  if (isSafetyNews(newsLines)) {
    const safetyLine =
      "Ada indikasi berita bertema keamanan belakangan ini. Lebih baik batasi aktivitas malam dan pastikan rumah terkunci dengan baik sebelum tidur.";
    if (lines.length === 3 && !lines.some((line) => line.toLowerCase().includes("keamanan"))) {
      lines = [lines[0], safetyLine, lines[2]];
    }
  }

  return lines.join("\n");
}

function getJakartaDateStamp(date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Jakarta",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

async function readCache(): Promise<InsightCache | null> {
  try {
    const raw = await fs.readFile(INSIGHTS_CACHE_PATH, "utf-8");
    const parsed = JSON.parse(raw) as InsightCache;
    if (!parsed?.date || !parsed?.text) return null;
    return parsed;
  } catch {
    return null;
  }
}

async function writeCache(cache: InsightCache): Promise<void> {
  await fs.writeFile(INSIGHTS_CACHE_PATH, JSON.stringify(cache), "utf-8");
}

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const todayStamp = getJakartaDateStamp();
  const cached = await readCache();
  if (cached && cached.date === todayStamp) {
    return NextResponse.json({ text: cached.text });
  }

  const baseUrl = process.env.NEXT_PUBLIC_BACKEND_URL;
  const geminiKey = process.env.GEMINI_API_KEY;
  const gnewsKey = process.env.GNEWS_API_KEY;

  if (!baseUrl) {
    if (cached?.text) return NextResponse.json({ text: cached.text });
    return NextResponse.json({ error: "NEXT_PUBLIC_BACKEND_URL belum di-set." }, { status: 500 });
  }
  if (!geminiKey) {
    if (cached?.text) return NextResponse.json({ text: cached.text });
    return NextResponse.json({ error: "GEMINI_API_KEY belum di-set." }, { status: 500 });
  }
  if (!gnewsKey) {
    if (cached?.text) return NextResponse.json({ text: cached.text });
    return NextResponse.json({ error: "GNEWS_API_KEY belum di-set." }, { status: 500 });
  }

  let history: BackendEvent[] = [];
  let historyError: string | null = null;
  try {
    const historyUrl = `${baseUrl.replace(/\/$/, "")}/api/history?limit=200`;
    const res = await fetch(historyUrl, { cache: "no-store" });
    if (!res.ok) {
      historyError = `history HTTP ${res.status}`;
    } else {
      history = (await res.json()) as BackendEvent[];
    }
  } catch (err) {
    historyError = (err as Error).message;
  }

  let news: NewsArticle[] = [];
  let newsError: string | null = null;
  try {
    const newsUrl = new URL("https://gnews.io/api/v4/top-headlines");
    newsUrl.search = new URLSearchParams({
      country: "id",
      lang: "id",
      max: "5",
      apikey: gnewsKey,
    }).toString();

    const res = await fetch(newsUrl.toString(), { cache: "no-store" });
    if (!res.ok) {
      newsError = `news HTTP ${res.status}`;
    } else {
      const payload = (await res.json()) as { articles?: NewsArticle[] };
      news = payload.articles ?? [];
    }
  } catch (err) {
    newsError = (err as Error).message;
  }

  const summary = buildSummary(history);
  const newsLines = news.slice(0, 5).map(formatNewsLine);
  const styleSeed = hashString(
    `${todayStamp}-${summary.total}-${summary.inCount}-${summary.outCount}-${summary.personInCount}-${summary.personOutCount}`,
  );
  const prompt = buildPrompt(summary, newsLines, styleSeed, historyError, newsError);

  const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;
  const geminiRes = await fetch(geminiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": geminiKey,
    },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.6,
        maxOutputTokens: 512,
      },
    }),
  });

  if (!geminiRes.ok) {
    const text = await geminiRes.text();
    if (cached?.text) return NextResponse.json({ text: cached.text });
    return NextResponse.json({ error: `Gemini error: ${geminiRes.status} ${text}` }, { status: 500 });
  }

  const data = (await geminiRes.json()) as {
    candidates?: Array<{
      content?: { parts?: Array<{ text?: string }> };
    }>;
  };

  const text = data.candidates?.[0]?.content?.parts?.map((p) => p.text ?? "").join("").trim();

  if (!text) {
    if (cached?.text) return NextResponse.json({ text: cached.text });
    return NextResponse.json({ error: "Gemini tidak mengembalikan teks." }, { status: 500 });
  }

  const normalizedText = normalizeInsightText(text, summary, newsLines, styleSeed);

  await writeCache({ date: todayStamp, text: normalizedText, updatedAt: new Date().toISOString() });
  return NextResponse.json({ text: normalizedText });
}
