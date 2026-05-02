import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  FileImage,
  FileText,
  FlaskConical,
  ImagePlus,
  MonitorUp,
  Play,
  RefreshCw,
  Settings,
  Upload,
} from "lucide-react";
import "./styles.css";

type Mode = "auto" | "ppt" | "poster" | "research_figure" | "edit";

type Session = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type Source = {
  id: string;
  filename: string;
  kind: string;
  summary: string;
};

type Job = {
  id: string;
  mode: Mode;
  resolved_mode?: Mode;
  status: string;
  prompt: string;
  error?: string;
  created_at: string;
};

type Artifact = {
  id: string;
  job_id: string;
  kind: string;
  label: string;
  path: string;
  mime_type: string;
};

type Catalog = {
  selected: string;
  provider: string;
  options: Array<{ selection: string; label: string; provider: string; model: string }>;
};

type SenseNovaStatus = {
  repo: string;
  huggingface_url: string;
  model_dir: string;
  source_dir: string;
  source_repo: string;
  source_exists: boolean;
  source_downloaded: boolean;
  source_error: string;
  exists: boolean;
  config: boolean;
  index: boolean;
  safetensors: number;
};

const API = "/api";

const modes: Array<{ id: Mode; label: string; icon: React.ReactNode; hint: string }> = [
  { id: "auto", label: "自动", icon: <Bot size={18} />, hint: "LLM 判断意图并分发" },
  { id: "ppt", label: "PPT", icon: <MonitorUp size={18} />, hint: "逐页整图生成后合成" },
  { id: "poster", label: "海报", icon: <FileImage size={18} />, hint: "单张完整大型海报" },
  { id: "research_figure", label: "科研绘图", icon: <FlaskConical size={18} />, hint: "架构图/原理图/3D图" },
  { id: "edit", label: "二次编辑", icon: <ImagePlus size={18} />, hint: "基于参考图重绘调整" },
];

function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [mode, setMode] = useState<Mode>("auto");
  const [prompt, setPrompt] = useState("");
  const [pageCount, setPageCount] = useState(8);
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [imageSize, setImageSize] = useState("2K");
  const [events, setEvents] = useState<string[]>([]);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [snStatus, setSnStatus] = useState<SenseNovaStatus | null>(null);
  const [downloadLog, setDownloadLog] = useState("");
  const [configText, setConfigText] = useState("");

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    const sessionRows = await getJson<Session[]>("/sessions");
    setSessions(sessionRows);
    if (sessionRows.length) {
      await loadSession(sessionRows[0].id);
    } else {
      const created = await postJson<Session>("/sessions", { title: "Open_Notebook Session" });
      setSessions([created]);
      await loadSession(created.id);
    }
    await loadCatalog();
    await loadSenseNovaStatus();
  }

  async function loadSession(id: string) {
    const data = await getJson<{ session: Session; sources: Source[]; jobs: Job[] }>(`/sessions/${id}`);
    setSession(data.session);
    setSources(data.sources);
    setJobs(data.jobs);
    setActiveJob(data.jobs[0] ?? null);
    if (data.jobs[0]) await loadJob(data.jobs[0].id);
  }

  async function newSession() {
    const created = await postJson<Session>("/sessions", { title: "Open_Notebook Session" });
    setSessions([created, ...sessions]);
    await loadSession(created.id);
  }

  async function uploadFiles(files: FileList | null) {
    if (!session || !files) return;
    for (const file of Array.from(files)) {
      const body = new FormData();
      body.append("file", file);
      await fetch(`${API}/sessions/${session.id}/sources`, { method: "POST", body });
    }
    await loadSession(session.id);
  }

  async function createJob() {
    if (!session || !prompt.trim()) return;
    const options: Record<string, unknown> = { image_size: imageSize };
    if (mode === "ppt") options.page_count = pageCount;
    if (mode === "poster" || mode === "research_figure" || mode === "edit") options.aspect_ratio = aspectRatio;
    const job = await postJson<Job>(`/sessions/${session.id}/jobs`, {
      mode,
      prompt,
      source_ids: sources.map((s) => s.id),
      options,
    });
    setActiveJob(job);
    setEvents([`任务已创建：${job.id}`]);
    subscribeJob(job.id);
    await loadSession(session.id);
  }

  function subscribeJob(jobId: string) {
    const evt = new EventSource(`${API}/jobs/${jobId}/events`);
    evt.onmessage = (event) => {
      appendEvent(event.data);
    };
    ["status", "route", "digest", "progress", "artifact", "exports", "completed", "failed"].forEach((name) => {
      evt.addEventListener(name, (event) => {
        appendEvent((event as MessageEvent).data);
        if (name === "completed" || name === "failed") {
          evt.close();
          void loadJob(jobId);
          if (session) void loadSession(session.id);
        }
      });
    });
  }

  function appendEvent(raw: string) {
    try {
      const data = JSON.parse(raw);
      setEvents((prev) => [data.message || data.error || data.reason || JSON.stringify(data), ...prev].slice(0, 80));
    } catch {
      setEvents((prev) => [raw, ...prev].slice(0, 80));
    }
  }

  async function loadJob(jobId: string) {
    const data = await getJson<{ job: Job; artifacts: Artifact[] }>(`/jobs/${jobId}`);
    setActiveJob(data.job);
    setArtifacts(data.artifacts);
  }

  async function loadCatalog() {
    const data = await getJson<Catalog>("/settings/llm/catalog");
    setCatalog(data);
  }

  async function loadSenseNovaStatus() {
    const data = await getJson<SenseNovaStatus>("/settings/sensenova/status");
    setSnStatus(data);
  }

  async function downloadSenseNova() {
    setDownloadLog("开始下载 SenseNova-U1-8B-MoT 到 models/Full。这个模型很大，请保持页面和服务运行。");
    const res = await postJson<Record<string, unknown>>("/settings/sensenova/download", {});
    setDownloadLog(JSON.stringify(res, null, 2));
    await loadSenseNovaStatus();
  }

  async function importConfig() {
    if (!configText.trim()) return;
    const parsed = JSON.parse(configText);
    const data = await postJson<Catalog>("/settings/llm/import", parsed);
    setCatalog(data);
    setConfigText("");
  }

  async function selectModel(selection: string) {
    const data = await postJson<Catalog>("/settings/llm/select", { selection });
    setCatalog(data);
  }

  const selectedSources = useMemo(() => sources.map((s) => s.filename).join(", "), [sources]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="mark">ON</div>
          <div>
            <h1>Open_Notebook</h1>
            <p>SenseNova full-canvas workspace</p>
          </div>
        </div>
        <button className="primary" onClick={newSession}>
          <FileText size={16} /> 新建 Session
        </button>
        <div className="section-title">Sessions</div>
        <div className="session-list">
          {sessions.map((s) => (
            <button
              key={s.id}
              className={session?.id === s.id ? "session active" : "session"}
              onClick={() => loadSession(s.id)}
            >
              <span>{s.title}</span>
              <small>{new Date(s.updated_at).toLocaleString()}</small>
            </button>
          ))}
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <strong>{session?.title ?? "Session"}</strong>
            <span>{session?.id}</span>
          </div>
          <div className="model-pill">
            <Settings size={15} />
            {catalog?.selected || "No model"}
          </div>
        </header>

        <section className="mode-grid">
          {modes.map((m) => (
            <button key={m.id} className={mode === m.id ? "mode selected" : "mode"} onClick={() => setMode(m.id)}>
              {m.icon}
              <span>{m.label}</span>
              <small>{m.hint}</small>
            </button>
          ))}
        </section>

        <section className="composer">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="输入你的需求；自动模式会先识别意图，PPT/海报/科研绘图/二次编辑模式会直接执行对应流水线。"
          />
          <div className="controls">
            {mode === "ppt" && (
              <label>
                页数
                <input type="number" min={1} max={60} value={pageCount} onChange={(e) => setPageCount(Number(e.target.value))} />
              </label>
            )}
            {mode !== "ppt" && (
              <label>
                比例
                <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
                  <option>9:16</option>
                  <option>16:9</option>
                  <option>1:1</option>
                  <option>4:3</option>
                  <option>3:4</option>
                  <option>3:2</option>
                  <option>2:3</option>
                </select>
              </label>
            )}
            <label>
              尺寸
              <select value={imageSize} onChange={(e) => setImageSize(e.target.value)}>
                <option>2K</option>
                <option>1K</option>
              </select>
            </label>
            <button className="run" onClick={createJob}>
              <Play size={17} /> 执行
            </button>
          </div>
        </section>

        <section className="panels">
          <div className="panel">
            <div className="panel-head">
              <h2>Sources</h2>
              <label className="upload">
                <Upload size={16} /> 上传
                <input type="file" multiple onChange={(e) => uploadFiles(e.target.files)} />
              </label>
            </div>
            {sources.length === 0 ? <p className="empty">尚未上传资料</p> : null}
            {sources.map((s) => (
              <div className="source" key={s.id}>
                <strong>{s.filename}</strong>
                <small>{s.kind}</small>
                <p>{s.summary}</p>
              </div>
            ))}
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>Progress</h2>
              <button className="ghost" onClick={() => activeJob && loadJob(activeJob.id)}>
                <RefreshCw size={15} />
              </button>
            </div>
            <div className="job-state">
              <strong>{activeJob?.status ?? "idle"}</strong>
              <span>{activeJob?.resolved_mode ?? activeJob?.mode ?? "no job"}</span>
            </div>
            <div className="events">
              {events.map((e, idx) => (
                <div key={idx}>{e}</div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>Artifacts</h2>
            </div>
            {artifacts.length === 0 ? <p className="empty">生成后会显示下载项</p> : null}
            {artifacts.map((a) => (
              <a className="artifact" href={`${API}/artifacts/${a.id}/download`} key={a.id}>
                <span>{a.label}</span>
                <small>{a.kind}</small>
              </a>
            ))}
          </div>
        </section>
      </main>

      <aside className="settings">
        <h2>LLM 配置</h2>
        <p className="muted">兼容 Clouds_Coder 的 profiles/model_profiles/扁平 provider 配置。</p>
        <select value={catalog?.selected ?? ""} onChange={(e) => selectModel(e.target.value)}>
          {catalog?.options.map((o) => (
            <option key={o.selection} value={o.selection}>
              {o.label}
            </option>
          ))}
        </select>
        <textarea
          className="config"
          value={configText}
          onChange={(e) => setConfigText(e.target.value)}
          placeholder='粘贴 LLM.config.json，例如 {"profiles":[...],"default_profile_id":"..."}'
        />
        <button className="primary" onClick={importConfig}>
          导入配置
        </button>
        <a className="download-config" href={`${API}/settings/llm/export`} target="_blank">
          导出当前配置
        </a>
        <div className="sn-box">
          <h2>SenseNova 模型</h2>
          <p className="muted">权重使用 models/Full；U1 源码默认映射到仓库外 ../SenseNova-U1-main。</p>
          <div className="status-grid">
            <span>目录</span>
            <strong>{snStatus?.model_dir ?? "models/Full"}</strong>
            <span>源码</span>
            <strong>{snStatus?.source_exists ? "ready" : "missing"}</strong>
            <span>路径</span>
            <strong>{snStatus?.source_dir ?? "../SenseNova-U1-main/src"}</strong>
            <span>权重</span>
            <strong>{snStatus?.safetensors ?? 0} / 8</strong>
            <span>配置</span>
            <strong>{snStatus?.config && snStatus?.index ? "ready" : "missing"}</strong>
          </div>
          {snStatus?.source_downloaded ? <p className="muted">已自动获取 SenseNova-U1 源码映射。</p> : null}
          {snStatus?.source_error ? <p className="muted">{snStatus.source_error}</p> : null}
          <a className="download-config" href={snStatus?.huggingface_url ?? "https://huggingface.co/sensenova/SenseNova-U1-8B-MoT"} target="_blank">
            HuggingFace 下载页
          </a>
          <button className="primary" onClick={downloadSenseNova}>
            下载到 models/Full
          </button>
          {downloadLog ? <pre className="download-log">{downloadLog}</pre> : null}
        </div>
        <div className="source-summary">当前资料：{selectedSources || "无"}</div>
      </aside>
    </div>
  );
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

createRoot(document.getElementById("root")!).render(<App />);
