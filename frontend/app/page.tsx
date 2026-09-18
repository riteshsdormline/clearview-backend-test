"use client";

import { useRef, useState } from "react";

type Detection = {
  detector_label: string;
  detector_confidence: number;
  scuff_score: number;
  severity: "scuffed" | "possible" | "ok";
  best_guess: string;
};

type AnalyzeResponse = {
  report: {
    dehazed?: boolean;
    num_objects_detected: number;
    num_scuffed: number;
    num_possible: number;
    detections: Detection[];
  };
  original_image_base64: string;
  original_image_content_type: string;
  modified_image_base64: string;
  annotated_image_base64: string;
  processing_seconds: number;
};

function imageUrl(type: string, data: string) {
  return `data:${type};base64,${data}`;
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0.65);
  const [detector, setDetector] = useState<"voc" | "regions">("voc");
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  function selectFile(nextFile?: File) {
    if (!nextFile || !nextFile.type.startsWith("image/")) return;
    setFile(nextFile);
    setPreview(URL.createObjectURL(nextFile));
    setResult(null);
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("image", file);
      form.append("threshold", String(threshold));
      form.append("detector", detector);
      const response = await fetch("/api/analyze", { method: "POST", body: form });
      const responseText = await response.text();
      let data: Partial<AnalyzeResponse> & { error?: string } = {};
      if (responseText) {
        try {
          data = JSON.parse(responseText);
        } catch {
          throw new Error(`Analysis service returned an invalid response (${response.status})`);
        }
      }
      if (!response.ok) throw new Error(data?.error || "Analysis failed");
      setResult(data as AnalyzeResponse);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not analyze image");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">CV</span>Clearview</div>
        <span className="status"><i /> inspection studio</span>
      </header>
      <section className="intro">
        <p className="eyebrow">Visual condition analysis</p>
        <h1>See what the image is hiding.</h1>
        <p className="lede">Upload a photo and Clearview will enhance the scene, detect objects, and surface signs of visible wear.</p>
      </section>
      <section className="workspace">
        <form className="control-panel" onSubmit={submit}>
          <div className="panel-heading"><span>01</span><h2>Source image</h2></div>
          <button className={`dropzone${dragging ? " is-dragging" : ""}${preview ? " has-preview" : ""}`} type="button" onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0]); }}>
            {preview ? <img src={preview} alt="Selected preview" /> : <><span className="upload-icon">+</span><strong>Drop an image here</strong><small>or click to browse · JPG, PNG, WEBP</small></>}
          </button>
          <input ref={inputRef} hidden type="file" accept="image/*" onChange={(event) => selectFile(event.target.files?.[0])} />
          {file && <div className="file-name"><span>{file.name}</span><button type="button" onClick={() => { setFile(null); setPreview(null); }}>Remove</button></div>}
          <div className="panel-heading settings-heading"><span>02</span><h2>Inspection settings</h2></div>
          <label className="field-label">Sensitivity <b>{threshold.toFixed(2)}</b></label>
          <input className="range" type="range" min={0.2} max={0.9} step={0.05} value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
          <div className="range-ends"><span>fewer alerts</span><span>more alerts</span></div>
          <label className="field-label" htmlFor="detector">Detection mode</label>
          <select id="detector" className="select" value={detector} onChange={(event) => setDetector(event.target.value as "voc" | "regions")}><option value="voc">Standard objects</option><option value="regions">Mixed item regions</option></select>
          <button className="analyze-button" type="submit" disabled={!file || loading}>{loading ? <><span className="spinner" /> Processing image</> : <>Run inspection <span>↗</span></>}</button>
          {loading && <p className="wait-note">The first request may take up to a minute while the service wakes.</p>}
          {error && <div className="error-box">{error}</div>}
        </form>
        <section className="results-panel">
          <div className="panel-heading"><span>03</span><h2>Inspection result</h2>{result && <span className="result-time">{result.processing_seconds}s</span>}</div>
          {result ? <ResultView result={result} /> : <div className="empty-result"><div className="crosshair">+</div><h3>Your result will appear here</h3><p>Clearview returns a clean enhancement, annotated findings, and a readable condition report.</p></div>}
        </section>
      </section>
    </main>
  );
}

function ResultView({ result }: { result: AnalyzeResponse }) {
  const { report } = result;
  const stats = [["Objects", report.num_objects_detected, "neutral"], ["Scuffed", report.num_scuffed, "red"], ["Possible wear", report.num_possible, "amber"]];
  return <>
    <div className="stats">{stats.map(([label, value, tone]) => <div className={`stat ${tone}`} key={label as string}><span>{label}</span><strong>{value}</strong></div>)}</div>
    <div className="image-grid"><ImageCard title="Enhanced view" src={imageUrl("image/jpeg", result.modified_image_base64)} download="clearview-enhanced.jpg" /><ImageCard title="Annotated findings" src={imageUrl("image/jpeg", result.annotated_image_base64)} download="clearview-annotated.jpg" /></div>
    <div className="result-meta"><span>{report.dehazed ? "Haze correction applied" : "Natural clarity retained"}</span><span>{report.detections.length} detections reviewed</span></div>
    <div className="findings">{report.detections.map((d, index) => <div className="finding" key={`${d.best_guess}-${index}`}><span className={`severity ${d.severity}`} /><strong>{d.best_guess}</strong><span className="finding-status">{d.severity}</span><span className="score">{d.scuff_score.toFixed(2)}</span></div>)}</div>
  </>;
}

function ImageCard({ title, src, download }: { title: string; src: string; download: string }) {
  return <figure className="image-card"><div className="image-card-title"><span>{title}</span><a href={src} download={download} aria-label={`Download ${title}`}>↓</a></div><img src={src} alt={title} /><figcaption>Download result <a href={src} download={download}>↓</a></figcaption></figure>;
}
