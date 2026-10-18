import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

interface ApodItem {
  date: string;
  title: string;
  explanation: string;
  media_type: string;
  url: string;
  hd_url: string;
  thumbnail_url: string;
  copyright: string;
  service_version: string;
}

interface GalleryResponse {
  items: ApodItem[];
  count: number;
  source: string;
  source_url: string;
  note: string;
  execution_time_s: number;
}

const COUNT_OPTIONS = [6, 9, 12, 18];

const TOPICS = [
  "nebula",
  "total solar eclipse",
  "comet",
  "supernova",
  "galaxy",
  "aurora",
  "moon",
  "mars",
];

export default function CelestialGallery() {
  const [count, setCount] = useState(9);
  const [topic, setTopic] = useState("nebula");
  const [data, setData] = useState<GalleryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lightbox, setLightbox] = useState<number | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const items = data?.items ?? [];
  const active = lightbox !== null ? items[lightbox] ?? null : null;

  const load = useCallback(async (n: number, t: string) => {
    setBusy(true);
    setError("");
    try {
      const resp = await api<GalleryResponse>("/api/labs/archive", {
        method: "POST",
        body: JSON.stringify({ archive: "apod", params: { count: n, q: t } }),
      });
      setData(resp);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(count, topic);
  }, [count, topic, load]);

  const closeLightbox = useCallback(() => setLightbox(null), []);

  const stepLightbox = useCallback(
    (delta: number) => {
      setLightbox((i) =>
        i === null || items.length === 0
          ? i
          : (i + delta + items.length) % items.length,
      );
    },
    [items.length],
  );

  // A freshly fetched set invalidates an open lightbox index.
  useEffect(() => {
    setLightbox(null);
  }, [data]);

  // Keyboard navigation + scroll lock while the lightbox is open.
  useEffect(() => {
    if (lightbox === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setLightbox(null);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        stepLightbox(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        stepLightbox(-1);
      } else if (e.key === "Home") {
        e.preventDefault();
        setLightbox(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setLightbox(items.length - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [lightbox, stepLightbox, items.length]);

  // Focus the dialog on open; return focus to the card that opened it.
  useEffect(() => {
    if (lightbox === null) {
      if (triggerRef.current) {
        triggerRef.current.focus();
        triggerRef.current = null;
      }
    } else {
      dialogRef.current?.focus();
    }
  }, [lightbox]);

  return (
    <div className="space-y-5">
      <header>
        <div className="eyebrow">Real captured imagery</div>
        <h1 className="display mt-3">Celestial Gallery</h1>
        <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-slate-300">
          Genuine photographs of celestial and other events from NASA's Astronomy
          Picture of the Day, served through the platform's archive connector
          with on-disk caching. Every card links to the full-resolution original.
        </p>
      </header>

      <section className="card flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-400">
          Images per load
          <select
            className="input mt-1 w-36"
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          >
            {COUNT_OPTIONS.map((n) => (
              <option key={n} value={n}>{n} images</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-400">
          Topic (Image Library search)
          <select
            className="input mt-1 w-52"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          >
            {TOPICS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <button className="btn-primary" onClick={() => void load(count, topic)} disabled={busy}>
          {busy ? "Fetching…" : "Fetch fresh set"}
        </button>
        <span className="text-xs text-slate-500">
          {busy
            ? "Querying NASA APOD…"
            : data
              ? `${data.count} entries · ${data.execution_time_s}s · cached for 6 h`
              : ""}
        </span>
        {error && <span className="text-xs text-rose-500">{error}</span>}
      </section>

      {data && (
        <div className="text-[11px] leading-relaxed text-slate-400">
          <b>Source:</b>{" "}
          <a
            className="border-b border-slate-400 hover:opacity-60"
            href={data.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {data.source}
          </a>
          {" — "}
          {data.note}
        </div>
      )}

      {!data && !busy && !error && (
        <section className="card text-sm text-slate-500">
          Fetch a set of real captured celestial images to begin.
        </section>
      )}

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item, idx) => (
          <article key={item.date + item.title} className="card flex flex-col gap-3">
            <button
              type="button"
              className="block w-full cursor-zoom-in text-left"
              aria-label={`Open "${item.title}" full screen`}
              onClick={(e) => {
                triggerRef.current = e.currentTarget;
                setLightbox(idx);
              }}
            >
              {item.media_type === "image" ? (
                <img
                  src={item.url}
                  alt={item.title}
                  loading="lazy"
                  className="max-h-72 w-full bg-slate-900 object-cover"
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : item.thumbnail_url ? (
                <img
                  src={item.thumbnail_url}
                  alt={`${item.title} (video preview)`}
                  loading="lazy"
                  className="max-h-72 w-full bg-slate-900 object-cover"
                />
              ) : (
                <div className="flex h-40 items-center justify-center bg-slate-900 text-xs uppercase tracking-[0.14em] text-slate-400">
                  Video — click to open
                </div>
              )}
            </button>

            <div className="flex items-baseline justify-between gap-2">
              <span className="eyebrow">{item.date}</span>
              {item.copyright && (
                <span className="text-[10px] text-slate-500">© {item.copyright}</span>
              )}
            </div>
            <h2 className="text-[17px] font-semibold leading-snug text-slate-200">
              {item.title}
            </h2>

            <details className="text-[13px] leading-relaxed text-slate-400">
              <summary className="cursor-pointer text-[11px] uppercase tracking-[0.14em] text-slate-500 hover:opacity-70">
                About this image
              </summary>
              <p className="mt-2">{item.explanation}</p>
            </details>

            <a
              className="mt-auto border-b border-slate-400 self-start text-[12px] uppercase tracking-[0.14em] hover:opacity-60"
              href={item.hd_url}
              target="_blank"
              rel="noreferrer"
            >
              {item.media_type === "image" ? "View full resolution (HD)" : "Open video"} ↗
            </a>
          </article>
        ))}
      </div>

      {lightbox !== null && active && (
        <div
          ref={dialogRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label={`${active.title} — ${lightbox + 1} of ${items.length}`}
          className="dark-scope fixed inset-0 z-50 flex flex-col bg-black/95 p-4 outline-none md:p-8"
          onClick={(e) => {
            if (e.currentTarget === e.target) closeLightbox();
          }}
        >
          <div className="flex items-start justify-between gap-4 border-b border-slate-700 pb-3">
            <div className="min-w-0">
              <span className="eyebrow">
                {active.date} · {lightbox + 1} / {items.length}
              </span>
              <h2 className="mt-1 truncate text-[17px] font-semibold text-slate-100">
                {active.title}
              </h2>
            </div>
            <button className="btn-ghost" onClick={closeLightbox} aria-label="Close lightbox (Esc)">
              Close
            </button>
          </div>

          <div className="flex min-h-0 flex-1 items-center justify-center py-4">
            {active.media_type === "image" ? (
              <img
                src={active.hd_url || active.url}
                alt={active.title}
                className="max-h-full max-w-full object-contain"
              />
            ) : /\.(mp4|webm|ogv|ogg|mov)(\?.*)?$/i.test(active.url) ? (
              <video src={active.url} controls autoPlay className="max-h-full max-w-full" />
            ) : (
              <div className="flex flex-col items-center gap-4">
                {active.thumbnail_url && (
                  <img
                    src={active.thumbnail_url}
                    alt={`${active.title} (video preview)`}
                    className="max-h-[50vh] object-contain"
                  />
                )}
                <a
                  className="border-b border-slate-400 text-[12px] uppercase tracking-[0.14em] text-slate-200 hover:opacity-60"
                  href={active.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open video ↗
                </a>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-700 pt-3">
            <div className="flex items-center gap-3">
              <button
                className="btn-ghost"
                onClick={() => stepLightbox(-1)}
                disabled={items.length < 2}
                aria-label="Previous image (arrow left)"
              >
                ← Prev
              </button>
              <button
                className="btn-ghost"
                onClick={() => stepLightbox(1)}
                disabled={items.length < 2}
                aria-label="Next image (arrow right)"
              >
                Next →
              </button>
              <span className="hidden text-[11px] uppercase tracking-[0.12em] text-slate-500 sm:inline">
                ← → navigate · Home / End jump · Esc close
              </span>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-slate-400">
              {active.copyright && <span>© {active.copyright}</span>}
              <a
                className="border-b border-slate-400 text-[12px] uppercase tracking-[0.14em] text-slate-200 hover:opacity-60"
                href={active.hd_url || active.url}
                target="_blank"
                rel="noreferrer"
              >
                {active.media_type === "image" ? "Full resolution (HD) ↗" : "Open ↗"}
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
