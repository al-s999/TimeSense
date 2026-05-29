"use client";

import type { FaceLandmarker } from "@mediapipe/tasks-vision";
import { useEffect, useMemo, useRef, useState } from "react";

type FaceInfo = {
  det_score?: number;
  bbox?: number[];
  [key: string]: unknown;
};

type EnrollResponse = {
  ok: boolean;
  identity?: string;
  count?: number;
  face_info?: FaceInfo;
  [key: string]: unknown;
};

type Status = "idle" | "loading" | "success" | "error";
type VerifyStep = "idle" | "position" | "blink" | "ready";

type Landmark = { x: number; y: number; z?: number };

const BLINK_CLOSE_THRESHOLD = 0.19;
const BLINK_OPEN_THRESHOLD = 0.23;

const LEFT_EYE = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];

function buildFormData(identity: string, file: File): FormData {
  const form = new FormData();
  form.append("identity", identity);
  form.append("image", file);
  return form;
}

async function enrollFace(
  backendUrl: string,
  identity: string,
  file: File
): Promise<EnrollResponse> {
  const form = buildFormData(identity, file);
  const res = await fetch(`${backendUrl}/enroll`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }

  return (await res.json()) as EnrollResponse;
}

function distance(a: Landmark, b: Landmark) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function eyeAspectRatio(landmarks: Landmark[], indices: number[]) {
  const p1 = landmarks[indices[0]];
  const p2 = landmarks[indices[1]];
  const p3 = landmarks[indices[2]];
  const p4 = landmarks[indices[3]];
  const p5 = landmarks[indices[4]];
  const p6 = landmarks[indices[5]];
  return (distance(p2, p6) + distance(p3, p5)) / (2 * distance(p1, p4));
}

export default function EnrollFacePage() {
  const [identity, setIdentity] = useState("me");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [response, setResponse] = useState<EnrollResponse | null>(null);
  const [verifyStep, setVerifyStep] = useState<VerifyStep>("idle");
  const [blinked, setBlinked] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [modelReady, setModelReady] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [isPreparing, setIsPreparing] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastVideoTimeRef = useRef<number>(-1);
  const blinkStateRef = useRef({ closed: false });
  const stableSinceRef = useRef<number | null>(null);

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

  const previewUrl = useMemo(() => {
    if (!file) return null;
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  const stopCamera = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraActive(false);
  };

  const resetVerification = () => {
    stopCamera();
    setVerifyStep("idle");
    setBlinked(false);
    setFaceDetected(false);
    stableSinceRef.current = null;
    blinkStateRef.current = { closed: false };
  };

  const loadLandmarker = async () => {
    if (landmarkerRef.current) return;
    setIsPreparing(true);
    try {
      const vision = await import("@mediapipe/tasks-vision");
      const resolver = await vision.FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.11/wasm"
      );
      const landmarker = await vision.FaceLandmarker.createFromOptions(
        resolver,
        {
          baseOptions: {
            modelAssetPath:
              "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
          },
          runningMode: "VIDEO",
          numFaces: 1,
        }
      );
      landmarkerRef.current = landmarker;
      setModelReady(true);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Gagal memuat model liveness."
      );
      setStatus("error");
    } finally {
      setIsPreparing(false);
    }
  };

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 720 },
          height: { ideal: 960 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Gagal mengakses kamera."
      );
      setStatus("error");
    }
  };

  const startVerification = async () => {
    setStatus("idle");
    setErrorMessage(null);
    setResponse(null);
    setFile(null);
    resetVerification();
    await loadLandmarker();
    if (!landmarkerRef.current) {
      return;
    }
    await startCamera();
    setVerifyStep("position");
  };

  const captureFrame = async () => {
    const video = videoRef.current;
    if (!video) return;
    const width = video.videoWidth || 720;
    const height = video.videoHeight || 960;
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setStatus("error");
      setErrorMessage("Tidak bisa membaca frame kamera.");
      return;
    }
    ctx.drawImage(video, 0, 0, width, height);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.9)
    );
    if (!blob) {
      setStatus("error");
      setErrorMessage("Gagal membuat gambar dari kamera.");
      return;
    }

    const captured = new File([blob], "capture.jpg", { type: "image/jpeg" });
    setFile(captured);
  };

  const handleEnroll = async () => {
    if (!file) {
      setStatus("error");
      setErrorMessage("Silakan ambil gambar dari kamera terlebih dulu.");
      return;
    }

    setStatus("loading");
    setErrorMessage(null);
    setResponse(null);

    try {
      const data = await enrollFace(backendUrl, identity, file);
      setResponse(data);
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Terjadi kesalahan."
      );
    }
  };

  useEffect(() => {
    if (!cameraActive || !landmarkerRef.current || verifyStep === "idle") {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      return;
    }

    const detect = () => {
      const video = videoRef.current;
      if (!video || video.readyState < 2) {
        rafRef.current = requestAnimationFrame(detect);
        return;
      }

      const now = performance.now();
      if (video.currentTime === lastVideoTimeRef.current) {
        rafRef.current = requestAnimationFrame(detect);
        return;
      }
      lastVideoTimeRef.current = video.currentTime;

      if (!landmarkerRef.current) {
        rafRef.current = requestAnimationFrame(detect);
        return;
      }

      const res = landmarkerRef.current.detectForVideo(video, now);
      const faces = res?.faceLandmarks ?? [];
      const landmarks = faces[0] as Landmark[] | undefined;

      if (!landmarks || landmarks.length === 0) {
        setFaceDetected(false);
        stableSinceRef.current = null;
        rafRef.current = requestAnimationFrame(detect);
        return;
      }

      setFaceDetected(true);

      if (verifyStep === "position") {
        if (!stableSinceRef.current) {
          stableSinceRef.current = now;
        } else if (now - stableSinceRef.current > 1200) {
          setVerifyStep("blink");
        }
      } else if (verifyStep === "blink") {
        const ear =
          (eyeAspectRatio(landmarks, LEFT_EYE) +
            eyeAspectRatio(landmarks, RIGHT_EYE)) /
          2;
        if (ear < BLINK_CLOSE_THRESHOLD) {
          blinkStateRef.current.closed = true;
        }
        if (ear > BLINK_OPEN_THRESHOLD && blinkStateRef.current.closed) {
          blinkStateRef.current.closed = false;
          setBlinked(true);
          setVerifyStep("ready");
        }
      }

      rafRef.current = requestAnimationFrame(detect);
    };

    rafRef.current = requestAnimationFrame(detect);

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [cameraActive, verifyStep]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#FCEEEE] via-[#F8F9FB] to-[#F6F6F6] px-2 py-8">
      <div className="mx-auto w-full max-w-4xl flex flex-col gap-8">
        <header className="space-y-1 mb-2">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#F6C1C1]">Face Enrollment</p>
          <h1 className="text-3xl font-bold text-neutral-900 drop-shadow-sm">Daftarkan wajah dengan verifikasi liveness</h1>
          <p className="text-sm text-neutral-500">Kamera wajib aktif. Ikuti instruksi posisi stabil dan berkedip sebelum mengambil foto verifikasi.</p>
        </header>

        <section className="rounded-3xl border border-[#F6C1C1]/30 bg-white/90 p-7 shadow-lg backdrop-blur-md">
          <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-6">
              <label className="grid gap-2 text-sm font-semibold text-neutral-700">
                <span className="flex items-center gap-2">Identity <span className="text-xs text-neutral-400">(Nama/ID)</span></span>
                <input
                  value={identity}
                  onChange={(e) => setIdentity(e.target.value)}
                  className="rounded-xl border border-[#F6C1C1]/40 px-3 py-2 text-sm text-neutral-900 shadow focus:border-[#F6C1C1] focus:outline-none bg-white/80"
                  placeholder="me"
                />
              </label>

              <div className="rounded-2xl border border-[#F6C1C1]/30 bg-[#FFF6F6] p-4 text-sm text-neutral-700 flex items-center gap-3">
                <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[#F6C1C1]/30 text-[#F6C1C1] text-lg">💡</span>
                <div>
                  <div className="font-semibold mb-1">Instruksi</div>
                  <ul className="list-disc pl-5 space-y-0.5 text-neutral-500 text-xs">
                    <li>Posisikan setengah badan menghadap kamera.</li>
                    <li>Wajah berada di dalam area oval.</li>
                    <li>Berkedip saat diminta.</li>
                  </ul>
                </div>
              </div>

              <div className="rounded-2xl border border-[#F6C1C1]/30 bg-white p-4 shadow flex flex-col gap-4">

                <div className="relative aspect-[3/4] w-full overflow-hidden rounded-xl bg-[#FCEEEE] border border-[#F6C1C1]/40">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="h-full w-full object-cover rounded-xl"
                  />
                  {/* Overlay gelap di luar oval */}
                  <svg
                    className="pointer-events-none absolute inset-0 w-full h-full"
                    viewBox="0 0 100 133"
                    preserveAspectRatio="none"
                  >
                    <defs>
                      <mask id="oval-mask">
                        <rect x="0" y="0" width="100" height="133" fill="white" />
                        <ellipse
                          cx="50"
                          cy="45"
                          rx="30"
                          ry="36"
                          fill="black"
                        />
                      </mask>
                    </defs>
                    <rect
                      x="0"
                      y="0"
                      width="100"
                      height="133"
                      fill="#000"
                      fillOpacity="0.55"
                      mask="url(#oval-mask)"
                    />
                    {/* Border oval */}
                    <ellipse
                      cx="50"
                      cy="45"
                      rx="30"
                      ry="36"
                      fill="none"
                      stroke="#F6C1C1"
                      strokeWidth="2"
                      opacity="0.7"
                    />
                  </svg>
                  <div className="pointer-events-none absolute inset-0">
                    <div className="absolute inset-6 rounded-2xl border border-white/60" />
                    {/* Area oval sudah digambar di SVG di atas */}
                    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-[#F6C1C1]/80 px-3 py-1 text-xs text-white shadow">Fokuskan kepala di area oval</div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 mt-2">
                  <button
                    type="button"
                    onClick={startVerification}
                    disabled={isPreparing}
                    className="rounded-xl bg-[#F6C1C1] px-5 py-2 text-sm font-semibold text-white shadow hover:bg-[#f8b3b3] transition disabled:opacity-60"
                  >
                    {isPreparing ? "Menyiapkan..." : "Mulai Verifikasi"}
                  </button>
                  <button
                    type="button"
                    onClick={captureFrame}
                    disabled={verifyStep !== "ready"}
                    className="rounded-xl border border-[#F6C1C1]/40 px-5 py-2 text-sm font-semibold text-[#F6C1C1] bg-white hover:bg-[#FFF6F6] transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Ambil Foto
                  </button>
                  <button
                    type="button"
                    onClick={resetVerification}
                    className="rounded-xl border border-neutral-200 px-5 py-2 text-sm font-semibold text-neutral-500 bg-white hover:bg-neutral-50 transition"
                  >
                    Reset
                  </button>
                </div>
              </div>

              {previewUrl ? (
                <div className="overflow-hidden rounded-xl border border-[#F6C1C1]/30 bg-white shadow">
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="h-64 w-full object-cover"
                  />
                </div>
              ) : (
                <div className="flex h-64 items-center justify-center rounded-xl border-2 border-dashed border-[#F6C1C1]/40 bg-[#FFF6F6] text-sm text-[#F6C1C1]">
                  Hasil capture akan muncul di sini
                </div>
              )}

              <button
                type="button"
                onClick={handleEnroll}
                disabled={status === "loading" || !file}
                className="inline-flex items-center justify-center rounded-xl bg-emerald-500 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-emerald-400 transition disabled:cursor-not-allowed disabled:opacity-60 mt-2"
              >
                {status === "loading" ? "Mengirim..." : "Enroll"}
              </button>
            </div>

            <div className="space-y-5">
              <div className="rounded-2xl border border-[#F6C1C1]/30 bg-[#FFF6F6] p-4 text-sm text-neutral-700 flex items-center gap-3">
                <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[#F6C1C1]/30 text-[#F6C1C1] text-lg">📷</span>
                <div>
                  <div className="font-semibold mb-1">Status Verifikasi</div>
                  <ul className="space-y-1 text-xs text-neutral-500">
                    <li>Kamera: <span className="font-semibold text-neutral-700">{cameraActive ? "Aktif" : "Belum aktif"}</span></li>
                    <li>Wajah terdeteksi: <span className="font-semibold text-neutral-700">{faceDetected ? "Ya" : "Tidak"}</span></li>
                    <li>Model liveness: <span className="font-semibold text-neutral-700">{modelReady ? "Siap" : "Belum siap"}</span></li>
                  </ul>
                </div>
              </div>

              <div className="rounded-2xl border border-[#F6C1C1]/30 bg-white p-4 text-sm text-neutral-700 flex items-center gap-3">
                <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[#F6C1C1]/30 text-[#F6C1C1] text-lg">✅</span>
                <div>
                  <div className="font-semibold mb-1">Checklist Liveness</div>
                  <ul className="space-y-1 text-xs text-neutral-500">
                    <li>{verifyStep === "position" || verifyStep === "blink" || verifyStep === "ready" ? <span className="text-emerald-500">✔</span> : <span className="text-neutral-300">○</span>} Posisikan wajah stabil</li>
                    <li>{blinked || verifyStep === "ready" ? <span className="text-emerald-500">✔</span> : <span className="text-neutral-300">○</span>} Berkedip sekali</li>
                    <li>{verifyStep === "ready" ? <span className="text-emerald-500">✔</span> : <span className="text-neutral-300">○</span>} Siap ambil foto</li>
                  </ul>
                </div>
              </div>

              <div className="rounded-2xl border border-[#F6C1C1]/30 bg-[#FFF6F6] p-4 text-sm text-neutral-700 flex items-center gap-3">
                <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[#F6C1C1]/30 text-[#F6C1C1] text-lg">📝</span>
                <div className="flex-1">
                  <div className="font-semibold mb-1">Status Enrollment</div>
                  <div className="text-xs">
                    {status === "idle" && "Siap untuk enroll."}
                    {status === "loading" && "Mengirim data ke server..."}
                    {status === "success" && <span className="text-emerald-500 font-semibold">Sukses!</span>}
                    {status === "error" && (
                      <span className="text-rose-600 font-semibold">{errorMessage ?? "Terjadi kesalahan."}</span>
                    )}
                  </div>
                  {status === "success" && response && (
                    <div className="mt-3 space-y-1 text-xs text-neutral-700">
                      <div><span className="font-semibold">Identity:</span> {response.identity ?? "-"}</div>
                      <div><span className="font-semibold">Count:</span> {response.count ?? "-"}</div>
                      {response.face_info && (
                        <div className="mt-2 rounded-lg border border-[#F6C1C1]/30 bg-white p-3">
                          <div className="font-semibold text-neutral-800 mb-1">Face Info</div>
                          <div className="text-xs text-neutral-500">
                            <div>det_score: {String(response.face_info.det_score ?? "-")}</div>
                            <div>bbox: {response.face_info.bbox ? JSON.stringify(response.face_info.bbox) : "-"}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        <footer className="text-xs text-neutral-400 mt-4 text-center">
          Backend URL: <span className="font-semibold">{backendUrl}</span>
        </footer>
      </div>
    </div>
  );
}
