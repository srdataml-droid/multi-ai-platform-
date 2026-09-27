"use client";

import { useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { api, post } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Count = { id: string; product: string; predicted: number | null; points: [number, number][]; confirmed: number | null; confirmed_at: string | null; synthetic_model: boolean; created_at: string };

const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm";

export default function StockPage() {
  const { data, error, refresh } = usePoll<{ items: Count[] }>("/stock/counts", 30000);
  const [product, setProduct] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ url: string; w: number; h: number } | null>(null);
  const [result, setResult] = useState<Count | null>(null);
  const [truth, setTruth] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pick = (f: File | null) => {
    setFile(f);
    setResult(null);
    if (preview) URL.revokeObjectURL(preview.url);
    if (!f) return setPreview(null);
    const url = URL.createObjectURL(f);
    const img = new Image();
    img.onload = () => setPreview({ url, w: img.naturalWidth, h: img.naturalHeight });
    img.src = url;
  };

  const count = async () => {
    if (!file || !product.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append("product", product.trim());
      form.append("photo", file);
      const r = await api<Count>("/stock/counts", { method: "POST", body: form });
      setResult(r);
      setTruth(r.predicted === null ? "" : String(r.predicted));
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!result || truth === "") return;
    setErr(null);
    try {
      setResult(await post<Count>(`/stock/counts/${result.id}/confirm`, { count: Number(truth) }));
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <ErrorLine error={error ?? err} />
      <Card title="Count stock from a photo">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Product<input data-testid="stock-product" className={input} placeholder="e.g. Cola 330ml" value={product} onChange={(e) => setProduct(e.target.value)} /></label>
          <label className="text-sm">Photo of the shelf
            <input data-testid="stock-photo" type="file" accept="image/*" capture="environment" className={input} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          </label>
        </div>
        <div className="mt-3"><Button onClick={count} disabled={busy || !file || !product.trim()}>{busy ? "Counting…" : "Count"}</Button></div>
        {preview && (
          <div className="relative mt-4 max-w-xl">
            {/* A local preview of the photo just taken (blob: URL); next/image cannot optimise it. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preview.url} alt="shelf" className="w-full rounded" />
            {result && (
              <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${preview.w} ${preview.h}`} preserveAspectRatio="none">
                {result.points.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={Math.max(preview.w, preview.h) / 90} fill="#dc2626" stroke="white" strokeWidth={2} />)}
              </svg>
            )}
          </div>
        )}
        {result && (
          <div className="mt-4 rounded border border-slate-200 p-3 text-sm" data-testid="stock-result">
            {result.predicted === null ? (
              <p>No counting model is available for your business yet. Enter the count yourself: every confirmed count teaches the next model.</p>
            ) : (
              <p>
                Counted <strong className="text-lg">{result.predicted}</strong> {result.product} (red dots show what was counted).
                {result.synthetic_model && <span className="ml-2"><Badge tone="amber">demo model trained on synthetic shelves</Badge></span>}
              </p>
            )}
            <div className="mt-2 flex items-end gap-2">
              <label className="text-sm">True count<input data-testid="stock-truth" type="number" min={0} className={`${input} w-28`} value={truth} onChange={(e) => setTruth(e.target.value)} /></label>
              <Button onClick={confirm} disabled={truth === ""}>{result.confirmed !== null ? "Update" : "Confirm"}</Button>
              {result.confirmed !== null && <Badge tone="green">saved: {result.confirmed}</Badge>}
            </div>
          </div>
        )}
      </Card>
      <Card title="Recent counts">
        {!data?.items.length ? <p className="text-sm text-slate-500">No counts yet.</p> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {data.items.map((c) => (
              <li key={c.id} className="flex items-center justify-between py-2">
                <span>{c.product} · {ago(c.created_at)}</span>
                <span className="flex items-center gap-2">
                  {c.predicted !== null && <span className="text-slate-500">counted {c.predicted}</span>}
                  {c.confirmed !== null ? <Badge tone={c.confirmed === c.predicted ? "green" : "amber"}>confirmed {c.confirmed}</Badge> : <Badge>not confirmed</Badge>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
