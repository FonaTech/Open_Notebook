import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUp,
  BarChart3,
  Bot,
  CheckCircle2,
  CircleAlert,
  FileImage,
  FileText,
  FlaskConical,
  ImagePlus,
  LayoutDashboard,
  MoreVertical,
  PanelLeft,
  PanelRight,
  Plus,
  Presentation,
  Settings,
  Share2,
  Sparkles,
} from "lucide-react";
import "./styles.css";

type Mode = "auto" | "ppt" | "poster" | "research_figure" | "edit";
type UiLanguage = "en" | "zh-CN" | "zh-TW" | "ja";
type OutputLanguage = "auto" | UiLanguage;

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

type Message = {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
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

type JobEvent = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  received_at: string;
};

type Catalog = {
  selected: string;
  provider: string;
  options: Array<{ selection: string; label: string; provider: string; model: string }>;
};

type SenseNovaStatus = {
  huggingface_url: string;
  model_dir: string;
  source_dir: string;
  source_exists: boolean;
  source_downloaded: boolean;
  source_error: string;
  exists: boolean;
  config: boolean;
  index: boolean;
  safetensors: number;
};

const i18n = {
  en: {
    languageEnglish: "English",
    languageSimplifiedChinese: "Simplified Chinese",
    languageTraditionalChinese: "Traditional Chinese",
    languageJapanese: "Japanese",
    outputAuto: "Auto",
    newNotebook: "Create notebook",
    runtimeStatus: "Run status",
    share: "Share",
    settings: "Settings",
    sources: "Sources",
    addSource: "Add source",
    sourceIntro: "Upload PDFs, images, tables, or text. The Agent will parse them and use them in chat.",
    emptySourcesTitle: "Saved sources will appear here",
    emptySourcesBody: "Use Add source to upload PDFs, images, text, or tables.",
    chat: "Chat",
    sourceCount: "{count} sources",
    welcomeHint: "Upload sources first, or tell the Agent what PPT, poster, or research figure you want.",
    composerPlaceholder: "Start typing... The Agent will parse files, clarify requirements through chat, and run generation when ready.",
    outputPrefs: "Output preferences",
    pages: "Pages",
    ratio: "Ratio",
    imageSize: "Image size",
    outputLanguage: "Output language",
    disclaimer: "Open_Notebook output may be inaccurate. Check source facts and text rendered inside images.",
    studio: "Studio",
    modeAuto: "Auto",
    modeAutoHint: "Agent clarifies and executes",
    modePpt: "Presentation",
    modePptHint: "Full-page image slides",
    modePoster: "Research poster",
    modePosterHint: "One complete large poster",
    modeResearch: "Research figure",
    modeResearchHint: "Architecture / mechanism / 3D",
    modeEdit: "Image edit",
    modeEditHint: "Redraw or adjust references",
    infographic: "Infographic",
    infographicHint: "Auto-routes to poster or figure",
    studioEmptyTitle: "Studio outputs will be saved here.",
    studioEmptyBody: "Add sources, then ask in chat. The Agent will generate when ready.",
    llmConfig: "LLM config",
    pasteConfig: "Paste LLM.config.json",
    importConfig: "Import",
    exportConfig: "Export",
    sourceReady: "source ready",
    sourceMissing: "source missing",
    hfDownloadPage: "HuggingFace page",
    downloadModel: "Download to models/Full",
    downloadStarted: "Started downloading SenseNova-U1-8B-MoT to models/Full. The model is large; keep the service running.",
    relatedJob: "Related job: {id}",
    jobTitle: "{mode} task · {status}",
    open: "Open",
    connectingEvents: "Connecting to task event stream...",
    localU1Note: "During local U1 generation, images are written only after each page completes.",
    noJobEvent: "Task created. Waiting for backend execution.",
    routeMessage: "Selected {mode} workflow",
    artifactMessage: "Generated {label}",
    exportsMessage: "Preparing PPTX/PDF exports",
    completedMessage: "Task completed",
    failedMessage: "Task failed",
    eventStatus: "Status",
    eventRoute: "Route",
    eventDigest: "Digest",
    eventProgress: "Progress",
    eventArtifact: "Artifact",
    eventExports: "Export",
    eventCompleted: "Done",
    eventFailed: "Failed",
    taskStarted: "Task started",
    digestingSources: "Digesting uploaded sources",
    planningPpt: "Planning {count} PPT pages",
    buildingPagePrompt: "Building prompt for page {page}/{total}",
    generatingSlide: "SenseNova is generating full slide {page}/{total}",
    planningPoster: "Planning complete poster",
    generatingPoster: "SenseNova is generating the complete poster",
    planningResearch: "Planning research figure / diagram",
    generatingResearch: "SenseNova is generating the complete research figure",
    planningEdit: "Building image-edit instructions",
    generatingEdit: "SenseNova is redrawing the image",
    statusPending: "Pending",
    statusRunning: "Running",
    statusCompleted: "Completed",
    statusFailed: "Failed",
    modeGenerate: "Generation",
  },
  "zh-CN": {
    languageEnglish: "英文",
    languageSimplifiedChinese: "简体中文",
    languageTraditionalChinese: "繁体中文",
    languageJapanese: "日文",
    outputAuto: "自动",
    newNotebook: "创建笔记本",
    runtimeStatus: "运行状态",
    share: "分享",
    settings: "设置",
    sources: "来源",
    addSource: "添加来源",
    sourceIntro: "上传 PDF、图片、表格或文本后，Agent 会自动解析并在对话中使用。",
    emptySourcesTitle: "已保存的来源将显示在此处",
    emptySourcesBody: "点击上方的“添加来源”即可添加 PDF、图片、文本或表格文件。",
    chat: "对话",
    sourceCount: "{count} 个来源",
    welcomeHint: "先上传资料，或直接告诉 Agent 你想生成的 PPT、海报或科研绘图。",
    composerPlaceholder: "开始输入... Agent 会解析文件并通过多轮对话明晰需求，需要生成时会自动执行。",
    outputPrefs: "输出偏好",
    pages: "页数",
    ratio: "比例",
    imageSize: "尺寸",
    outputLanguage: "输出语言",
    disclaimer: "Open_Notebook 生成内容可能不准确，请核查来源事实和图中文字。",
    studio: "Studio",
    modeAuto: "自动",
    modeAutoHint: "Agent 多轮澄清并执行",
    modePpt: "演示文稿",
    modePptHint: "逐页整图 PPT",
    modePoster: "科研海报",
    modePosterHint: "单张完整大型海报",
    modeResearch: "科研绘图",
    modeResearchHint: "架构图 / 原理图 / 3D 图",
    modeEdit: "二次编辑",
    modeEditHint: "参考图重绘调整",
    infographic: "信息图",
    infographicHint: "自动归入海报或科研绘图",
    studioEmptyTitle: "Studio 输出将保存在此处。",
    studioEmptyBody: "添加来源后，在对话中提出任务，Agent 会在需要时自动生成。",
    llmConfig: "LLM 配置",
    pasteConfig: "粘贴 LLM.config.json",
    importConfig: "导入配置",
    exportConfig: "导出",
    sourceReady: "源码 ready",
    sourceMissing: "源码 missing",
    hfDownloadPage: "HuggingFace 下载页",
    downloadModel: "下载到 models/Full",
    downloadStarted: "开始下载 SenseNova-U1-8B-MoT 到 models/Full。模型很大，请保持服务运行。",
    relatedJob: "关联任务：{id}",
    jobTitle: "{mode}任务 · {status}",
    open: "打开",
    connectingEvents: "正在连接任务事件流...",
    localU1Note: "本地 U1 生成期间不会逐步落图，单页完成后会自动出现下载项。",
    noJobEvent: "任务已创建，等待后端开始执行。",
    routeMessage: "已选择 {mode} 流程",
    artifactMessage: "已生成 {label}",
    exportsMessage: "正在整理 PPTX/PDF 导出文件",
    completedMessage: "任务完成",
    failedMessage: "任务失败",
    eventStatus: "状态",
    eventRoute: "分发",
    eventDigest: "解析",
    eventProgress: "进度",
    eventArtifact: "产物",
    eventExports: "导出",
    eventCompleted: "完成",
    eventFailed: "失败",
    taskStarted: "任务已启动",
    digestingSources: "正在整理上传资料",
    planningPpt: "正在规划 {count} 页 PPT",
    buildingPagePrompt: "正在生成第 {page}/{total} 页 prompt",
    generatingSlide: "SenseNova 正在生成第 {page}/{total} 页整图",
    planningPoster: "正在规划完整海报",
    generatingPoster: "SenseNova 正在生成完整大型海报",
    planningResearch: "正在规划科研绘图/架构图",
    generatingResearch: "SenseNova 正在生成完整科研图",
    planningEdit: "正在生成图片二次编辑指令",
    generatingEdit: "SenseNova 正在执行图片二次绘制",
    statusPending: "等待中",
    statusRunning: "运行中",
    statusCompleted: "已完成",
    statusFailed: "失败",
    modeGenerate: "生成",
  },
  "zh-TW": {
    languageEnglish: "英文",
    languageSimplifiedChinese: "簡體中文",
    languageTraditionalChinese: "繁體中文",
    languageJapanese: "日文",
    outputAuto: "自動",
    newNotebook: "建立筆記本",
    runtimeStatus: "執行狀態",
    share: "分享",
    settings: "設定",
    sources: "來源",
    addSource: "新增來源",
    sourceIntro: "上傳 PDF、圖片、表格或文字後，Agent 會自動解析並在對話中使用。",
    emptySourcesTitle: "已儲存的來源會顯示在這裡",
    emptySourcesBody: "點擊上方「新增來源」即可加入 PDF、圖片、文字或表格檔案。",
    chat: "對話",
    sourceCount: "{count} 個來源",
    welcomeHint: "先上傳資料，或直接告訴 Agent 你想生成的 PPT、海報或科研繪圖。",
    composerPlaceholder: "開始輸入... Agent 會解析檔案並透過多輪對話釐清需求，需要生成時會自動執行。",
    outputPrefs: "輸出偏好",
    pages: "頁數",
    ratio: "比例",
    imageSize: "尺寸",
    outputLanguage: "輸出語言",
    disclaimer: "Open_Notebook 生成內容可能不準確，請核查來源事實與圖片中的文字。",
    studio: "Studio",
    modeAuto: "自動",
    modeAutoHint: "Agent 多輪釐清並執行",
    modePpt: "簡報",
    modePptHint: "逐頁整圖 PPT",
    modePoster: "科研海報",
    modePosterHint: "單張完整大型海報",
    modeResearch: "科研繪圖",
    modeResearchHint: "架構圖 / 原理圖 / 3D 圖",
    modeEdit: "二次編輯",
    modeEditHint: "參考圖重繪調整",
    infographic: "資訊圖",
    infographicHint: "自動歸入海報或科研繪圖",
    studioEmptyTitle: "Studio 輸出會儲存在這裡。",
    studioEmptyBody: "新增來源後，在對話中提出任務，Agent 會在需要時自動生成。",
    llmConfig: "LLM 設定",
    pasteConfig: "貼上 LLM.config.json",
    importConfig: "匯入設定",
    exportConfig: "匯出",
    sourceReady: "原始碼 ready",
    sourceMissing: "原始碼 missing",
    hfDownloadPage: "HuggingFace 下載頁",
    downloadModel: "下載到 models/Full",
    downloadStarted: "開始下載 SenseNova-U1-8B-MoT 到 models/Full。模型很大，請保持服務執行。",
    relatedJob: "關聯任務：{id}",
    jobTitle: "{mode}任務 · {status}",
    open: "開啟",
    connectingEvents: "正在連接任務事件流...",
    localU1Note: "本地 U1 生成期間不會逐步落圖，單頁完成後會自動出現下載項。",
    noJobEvent: "任務已建立，等待後端開始執行。",
    routeMessage: "已選擇 {mode} 流程",
    artifactMessage: "已生成 {label}",
    exportsMessage: "正在整理 PPTX/PDF 匯出檔案",
    completedMessage: "任務完成",
    failedMessage: "任務失敗",
    eventStatus: "狀態",
    eventRoute: "分發",
    eventDigest: "解析",
    eventProgress: "進度",
    eventArtifact: "產物",
    eventExports: "匯出",
    eventCompleted: "完成",
    eventFailed: "失敗",
    taskStarted: "任務已啟動",
    digestingSources: "正在整理上傳資料",
    planningPpt: "正在規劃 {count} 頁 PPT",
    buildingPagePrompt: "正在生成第 {page}/{total} 頁 prompt",
    generatingSlide: "SenseNova 正在生成第 {page}/{total} 頁整圖",
    planningPoster: "正在規劃完整海報",
    generatingPoster: "SenseNova 正在生成完整大型海報",
    planningResearch: "正在規劃科研繪圖/架構圖",
    generatingResearch: "SenseNova 正在生成完整科研圖",
    planningEdit: "正在生成圖片二次編輯指令",
    generatingEdit: "SenseNova 正在執行圖片二次繪製",
    statusPending: "等待中",
    statusRunning: "執行中",
    statusCompleted: "已完成",
    statusFailed: "失敗",
    modeGenerate: "生成",
  },
  ja: {
    languageEnglish: "英語",
    languageSimplifiedChinese: "簡体字中国語",
    languageTraditionalChinese: "繁体字中国語",
    languageJapanese: "日本語",
    outputAuto: "自動",
    newNotebook: "ノートブックを作成",
    runtimeStatus: "実行状態",
    share: "共有",
    settings: "設定",
    sources: "ソース",
    addSource: "ソースを追加",
    sourceIntro: "PDF、画像、表、テキストをアップロードすると、Agent が解析して会話で利用します。",
    emptySourcesTitle: "保存されたソースがここに表示されます",
    emptySourcesBody: "上の「ソースを追加」から PDF、画像、テキスト、表を追加できます。",
    chat: "チャット",
    sourceCount: "{count} 件のソース",
    welcomeHint: "まず資料をアップロードするか、作成したい PPT、ポスター、研究図を Agent に伝えてください。",
    composerPlaceholder: "入力してください... Agent がファイルを解析し、対話で要件を確認して、準備できたら生成を実行します。",
    outputPrefs: "出力設定",
    pages: "ページ数",
    ratio: "比率",
    imageSize: "サイズ",
    outputLanguage: "出力言語",
    disclaimer: "Open_Notebook の生成内容は不正確な場合があります。出典事実と画像内テキストを確認してください。",
    studio: "Studio",
    modeAuto: "自動",
    modeAutoHint: "Agent が確認して実行",
    modePpt: "プレゼン",
    modePptHint: "ページ単位の画像スライド",
    modePoster: "研究ポスター",
    modePosterHint: "1枚の大型ポスター",
    modeResearch: "研究図",
    modeResearchHint: "構成図 / 原理図 / 3D 図",
    modeEdit: "画像編集",
    modeEditHint: "参照画像を再描画・調整",
    infographic: "インフォグラフィック",
    infographicHint: "ポスターまたは研究図へ自動振分",
    studioEmptyTitle: "Studio の出力はここに保存されます。",
    studioEmptyBody: "ソースを追加してからチャットで依頼すると、Agent が必要に応じて生成します。",
    llmConfig: "LLM 設定",
    pasteConfig: "LLM.config.json を貼り付け",
    importConfig: "インポート",
    exportConfig: "エクスポート",
    sourceReady: "ソース ready",
    sourceMissing: "ソース missing",
    hfDownloadPage: "HuggingFace ページ",
    downloadModel: "models/Full にダウンロード",
    downloadStarted: "SenseNova-U1-8B-MoT を models/Full にダウンロード開始。モデルは大きいため、サービスを起動したままにしてください。",
    relatedJob: "関連タスク：{id}",
    jobTitle: "{mode}タスク · {status}",
    open: "開く",
    connectingEvents: "タスクイベントストリームに接続中...",
    localU1Note: "ローカル U1 生成中は、各ページ完了後に画像が保存されます。",
    noJobEvent: "タスクを作成しました。バックエンドの実行開始を待っています。",
    routeMessage: "{mode} ワークフローを選択しました",
    artifactMessage: "{label} を生成しました",
    exportsMessage: "PPTX/PDF エクスポートを準備中",
    completedMessage: "タスク完了",
    failedMessage: "タスク失敗",
    eventStatus: "状態",
    eventRoute: "振分",
    eventDigest: "解析",
    eventProgress: "進捗",
    eventArtifact: "成果物",
    eventExports: "出力",
    eventCompleted: "完了",
    eventFailed: "失敗",
    taskStarted: "タスクを開始しました",
    digestingSources: "アップロード資料を整理中",
    planningPpt: "{count} ページの PPT を設計中",
    buildingPagePrompt: "{page}/{total} ページ目のプロンプトを作成中",
    generatingSlide: "SenseNova が {page}/{total} ページ目の全体画像を生成中",
    planningPoster: "完全なポスターを設計中",
    generatingPoster: "SenseNova が完全な大型ポスターを生成中",
    planningResearch: "研究図 / 構成図を設計中",
    generatingResearch: "SenseNova が完全な研究図を生成中",
    planningEdit: "画像編集指示を作成中",
    generatingEdit: "SenseNova が画像を再描画中",
    statusPending: "待機中",
    statusRunning: "実行中",
    statusCompleted: "完了",
    statusFailed: "失敗",
    modeGenerate: "生成",
  },
} as const;

type I18nKey = keyof typeof i18n.en;

const API = "/api";

const supportedUiLanguages: Array<{ id: UiLanguage; label: string }> = [
  { id: "en", label: "English" },
  { id: "zh-CN", label: "简体中文" },
  { id: "zh-TW", label: "繁體中文" },
  { id: "ja", label: "日本語" },
];

const outputLanguages: Array<{ id: OutputLanguage; key: I18nKey }> = [
  { id: "auto", key: "outputAuto" },
  { id: "en", key: "languageEnglish" },
  { id: "zh-CN", key: "languageSimplifiedChinese" },
  { id: "zh-TW", key: "languageTraditionalChinese" },
  { id: "ja", key: "languageJapanese" },
];

const studioModes: Array<{ id: Mode; titleKey: I18nKey; hintKey: I18nKey; icon: React.ReactNode }> = [
  { id: "auto", titleKey: "modeAuto", hintKey: "modeAutoHint", icon: <Bot size={18} /> },
  { id: "ppt", titleKey: "modePpt", hintKey: "modePptHint", icon: <Presentation size={18} /> },
  { id: "poster", titleKey: "modePoster", hintKey: "modePosterHint", icon: <FileImage size={18} /> },
  { id: "research_figure", titleKey: "modeResearch", hintKey: "modeResearchHint", icon: <FlaskConical size={18} /> },
  { id: "edit", titleKey: "modeEdit", hintKey: "modeEditHint", icon: <ImagePlus size={18} /> },
];

function App() {
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(() => detectInitialLanguage());
  const [outputLanguage, setOutputLanguage] = useState<OutputLanguage>(() => {
    const saved = localStorage.getItem("open_notebook_output_language");
    return isOutputLanguage(saved) ? saved : "auto";
  });
  const [sessions, setSessions] = useState<Session[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [artifactsByJob, setArtifactsByJob] = useState<Record<string, Artifact[]>>({});
  const [jobEventsById, setJobEventsById] = useState<Record<string, JobEvent[]>>({});
  const [mode, setMode] = useState<Mode>("auto");
  const [prompt, setPrompt] = useState("");
  const [pageCount, setPageCount] = useState(8);
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [imageSize, setImageSize] = useState("2K");
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [snStatus, setSnStatus] = useState<SenseNovaStatus | null>(null);
  const [downloadLog, setDownloadLog] = useState("");
  const [configText, setConfigText] = useState("");
  const [busy, setBusy] = useState(false);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const jobStreamsRef = useRef<Map<string, EventSource>>(new Map());
  const jobEventIdsRef = useRef<Map<string, Set<string>>>(new Map());
  const activeJobIdRef = useRef<string | null>(null);
  const jobEventCount = useMemo(
    () => Object.values(jobEventsById).reduce((total, rows) => total + rows.length, 0),
    [jobEventsById],
  );

  useEffect(() => {
    void bootstrap();
    return () => closeJobStreams();
  }, []);

  useEffect(() => {
    localStorage.setItem("open_notebook_ui_language", uiLanguage);
    document.documentElement.lang = uiLanguage;
  }, [uiLanguage]);

  useEffect(() => {
    localStorage.setItem("open_notebook_output_language", outputLanguage);
  }, [outputLanguage]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, jobEventCount]);

  useEffect(() => {
    activeJobIdRef.current = activeJob?.id ?? null;
  }, [activeJob?.id]);

  useEffect(() => {
    if (!session) return;
    const evt = new EventSource(`${API}/sessions/${session.id}/events`);
    evt.addEventListener("snapshot", (event) => {
      const data = JSON.parse((event as MessageEvent).data);
      if (Array.isArray(data.messages)) setMessages(data.messages);
      if (Array.isArray(data.jobs)) {
        setJobs(data.jobs);
        setActiveJob(data.jobs[0] ?? null);
        data.jobs.slice(0, 12).forEach((job: Job) => subscribeJob(job.id));
        if (data.jobs[0]) void loadJob(data.jobs[0].id, true);
      }
    });
    return () => evt.close();
  }, [session?.id]);

  async function bootstrap() {
    const sessionRows = await getJson<Session[]>("/sessions");
    setSessions(sessionRows);
    if (sessionRows.length) {
      await loadSession(sessionRows[0].id);
    } else {
      const created = await postJson<Session>("/sessions", { title: "Untitled notebook" });
      setSessions([created]);
      await loadSession(created.id);
    }
    await loadCatalog();
    await loadSenseNovaStatus();
  }

  async function loadSession(id: string) {
    if (session?.id && session.id !== id) {
      closeJobStreams();
      setJobEventsById({});
      setArtifactsByJob({});
      setArtifacts([]);
    }
    const data = await getJson<{ session: Session; sources: Source[]; jobs: Job[]; messages: Message[] }>(`/sessions/${id}`);
    setSession(data.session);
    setSources(data.sources);
    setJobs(data.jobs);
    setMessages(data.messages);
    setActiveJob(data.jobs[0] ?? null);
    data.jobs.slice(0, 12).forEach((job) => subscribeJob(job.id));
    if (data.jobs[0]) await loadJob(data.jobs[0].id, true);
  }

  async function newSession() {
    const created = await postJson<Session>("/sessions", { title: "Untitled notebook" });
    setSessions([created, ...sessions]);
    setMode("auto");
    setPrompt("");
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

  async function sendMessage() {
    if (!session || !prompt.trim() || busy) return;
    const content = prompt.trim();
    setPrompt("");
    setBusy(true);
    const options: Record<string, unknown> = {
      image_size: imageSize,
      output_language: outputLanguage,
      ui_language: uiLanguage,
    };
    if (mode === "ppt") options.page_count = pageCount;
    if (mode !== "ppt") options.aspect_ratio = aspectRatio;
    try {
      const data = await postJson<{ job?: Job }>(`/sessions/${session.id}/messages`, {
        content,
        mode_hint: mode,
        source_ids: sources.map((s) => s.id),
        options,
      });
      if (data.job) {
        setActiveJob(data.job);
        subscribeJob(data.job.id);
      }
      await loadSession(session.id);
    } finally {
      setBusy(false);
    }
  }

  function subscribeJob(jobId: string) {
    if (!jobId || jobStreamsRef.current.has(jobId)) return;
    const evt = new EventSource(`${API}/jobs/${jobId}/events`);
    jobStreamsRef.current.set(jobId, evt);
    jobEventIdsRef.current.set(jobId, jobEventIdsRef.current.get(jobId) ?? new Set());
    ["status", "route", "digest", "progress", "artifact", "exports", "completed", "failed"].forEach((name) => {
      evt.addEventListener(name, (event) => {
        handleJobEvent(jobId, name, event as MessageEvent);
        if (["artifact", "exports", "completed", "failed"].includes(name)) {
          void loadJob(jobId, activeJobIdRef.current === jobId);
        }
        if (name === "completed" || name === "failed") {
          evt.close();
          jobStreamsRef.current.delete(jobId);
        }
      });
    });
    evt.onerror = () => {
      evt.close();
      jobStreamsRef.current.delete(jobId);
    };
  }

  function handleJobEvent(jobId: string, type: string, event: MessageEvent) {
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(event.data) as Record<string, unknown>;
    } catch {
      payload = { message: event.data };
    }
    const dedupeKey = event.lastEventId || `${type}:${event.data}`;
    const seen = jobEventIdsRef.current.get(jobId) ?? new Set<string>();
    if (seen.has(dedupeKey)) return;
    seen.add(dedupeKey);
    jobEventIdsRef.current.set(jobId, seen);
    const row: JobEvent = {
      id: dedupeKey,
      type,
      payload,
      received_at: new Date().toISOString(),
    };
    setJobEventsById((prev) => {
      const rows = [...(prev[jobId] ?? []), row].slice(-80);
      return { ...prev, [jobId]: rows };
    });
  }

  function closeJobStreams() {
    for (const stream of jobStreamsRef.current.values()) stream.close();
    jobStreamsRef.current.clear();
    jobEventIdsRef.current.clear();
  }

  async function loadJob(jobId: string, makeActive = true) {
    const data = await getJson<{ job: Job; artifacts: Artifact[] }>(`/jobs/${jobId}`);
    setJobs((prev) => {
      const exists = prev.some((job) => job.id === data.job.id);
      const rows = exists ? prev.map((job) => (job.id === data.job.id ? data.job : job)) : [data.job, ...prev];
      return rows.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    });
    setArtifactsByJob((prev) => ({ ...prev, [jobId]: data.artifacts }));
    if (makeActive) {
      setActiveJob(data.job);
      setArtifacts(data.artifacts);
    }
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
    setDownloadLog(t("downloadStarted"));
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

  const t = (key: I18nKey, vars?: Record<string, string | number>) => translate(uiLanguage, key, vars);
  const sourceTitle = useMemo(() => t("sourceCount", { count: sources.length }), [sources.length, uiLanguage]);
  const latestJobs = jobs.slice(0, 4);
  const jobById = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);

  return (
    <div className="notebook-shell">
      <header className="appbar">
        <div className="app-title">
          <div className="logo-mark">ON</div>
          <input value={session?.title ?? "Untitled notebook"} readOnly aria-label="notebook title" />
        </div>
        <div className="app-actions">
          <label className="language-select">
            <span>{t("settings")}</span>
            <select value={uiLanguage} onChange={(e) => setUiLanguage(e.target.value as UiLanguage)}>
              {supportedUiLanguages.map((lang) => (
                <option key={lang.id} value={lang.id}>
                  {lang.label}
                </option>
              ))}
            </select>
          </label>
          <button className="black-pill" onClick={newSession}>
            <Plus size={18} /> {t("newNotebook")}
          </button>
          <button className="icon-button" title={t("runtimeStatus")}>
            <BarChart3 size={22} />
          </button>
          <button className="icon-button" title={t("share")}>
            <Share2 size={22} />
          </button>
          <button className="icon-button" title={t("settings")}>
            <Settings size={22} />
          </button>
          <span className="avatar">ON</span>
        </div>
      </header>

      <div className="notebook-grid">
        <aside className="card-pane sources-pane">
          <PaneHeader title={t("sources")} icon={<PanelLeft size={20} />} />
          <label className="add-source">
            <Plus size={18} /> {t("addSource")}
            <input type="file" multiple onChange={(e) => uploadFiles(e.target.files)} />
          </label>
          <div className="source-search">
            <Sparkles size={18} />
            <span>{t("sourceIntro")}</span>
          </div>
          <div className="source-list">
            {sources.length === 0 ? (
              <div className="empty-state">
                <FileText size={34} />
                <strong>{t("emptySourcesTitle")}</strong>
                <p>{t("emptySourcesBody")}</p>
              </div>
            ) : (
              sources.map((s) => (
                <div className="source-item" key={s.id}>
                  <FileText size={18} />
                  <div>
                    <strong>{s.filename}</strong>
                    <small>{s.kind}</small>
                    <p>{s.summary}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>

        <main className="card-pane chat-pane">
          <PaneHeader title={t("chat")} trailing={<MoreVertical size={22} />} />
          <section className="chat-scroll">
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="book-icon">📒</div>
                <h1>{session?.title ?? "Untitled notebook"}</h1>
                <p>{sourceTitle} · {new Date().toLocaleDateString()}</p>
                <span>{t("welcomeHint")}</span>
              </div>
            ) : (
              messages.map((m) => (
                <ChatMessage
                  key={m.id}
                  message={m}
                  job={typeof m.metadata?.job_id === "string" ? jobById.get(String(m.metadata.job_id)) : undefined}
                  events={
                    typeof m.metadata?.job_id === "string"
                      ? jobEventsById[String(m.metadata.job_id)] ?? []
                      : []
                  }
                  artifacts={
                    typeof m.metadata?.job_id === "string"
                      ? artifactsByJob[String(m.metadata.job_id)] ?? []
                      : []
                  }
                  onOpenJob={(jobId) => void loadJob(jobId, true)}
                  t={t}
                  language={uiLanguage}
                />
              ))
            )}
            <div ref={messageEndRef} />
          </section>
          <section className="composer-card">
            <div className="intent-row">
              {studioModes.map((item) => (
                <button
                  key={item.id}
                  className={mode === item.id ? "intent selected" : "intent"}
                  onClick={() => setMode(item.id)}
                >
                  {item.icon}
                  {t(item.titleKey)}
                </button>
              ))}
            </div>
            <div className="input-row">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void sendMessage();
                }}
                placeholder={t("composerPlaceholder")}
              />
              <div className="input-actions">
                <button className="send-button" onClick={sendMessage} disabled={busy || !prompt.trim()}>
                  <ArrowUp size={22} />
                </button>
              </div>
            </div>
            <div className="output-preferences">
              <span className="prefs-title">{t("outputPrefs")}</span>
              <label>
                <span>{mode === "ppt" ? t("pages") : t("ratio")}</span>
                {mode === "ppt" ? (
                  <input type="number" min={1} max={60} value={pageCount} onChange={(e) => setPageCount(Number(e.target.value))} aria-label={t("pages")} />
                ) : (
                  <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} aria-label={t("ratio")}>
                    <option>16:9</option>
                    <option>9:16</option>
                    <option>1:1</option>
                    <option>4:3</option>
                    <option>3:4</option>
                    <option>3:2</option>
                    <option>2:3</option>
                  </select>
                )}
              </label>
              <label>
                <span>{t("imageSize")}</span>
                <select value={imageSize} onChange={(e) => setImageSize(e.target.value)} aria-label={t("imageSize")}>
                  <option>2K</option>
                  <option>1K</option>
                </select>
              </label>
              <label>
                <span>{t("outputLanguage")}</span>
                <select value={outputLanguage} onChange={(e) => setOutputLanguage(e.target.value as OutputLanguage)} aria-label={t("outputLanguage")}>
                  {outputLanguages.map((lang) => (
                    <option key={lang.id} value={lang.id}>
                      {t(lang.key)}
                    </option>
                  ))}
                </select>
              </label>
              <span>{sourceTitle}</span>
            </div>
          </section>
          <footer className="disclaimer">{t("disclaimer")}</footer>
        </main>

        <aside className="card-pane studio-pane">
          <PaneHeader title={t("studio")} icon={<PanelRight size={20} />} />
          <div className="studio-grid">
            {studioModes.slice(1).map((item) => (
              <button key={item.id} className={mode === item.id ? "studio-tile active" : "studio-tile"} onClick={() => setMode(item.id)}>
                {item.icon}
                <strong>{t(item.titleKey)}</strong>
                <small>{t(item.hintKey)}</small>
              </button>
            ))}
            <button className="studio-tile muted-tile">
              <LayoutDashboard size={18} />
              <strong>{t("infographic")}</strong>
              <small>{t("infographicHint")}</small>
            </button>
          </div>

          <section className="studio-output">
            {latestJobs.length === 0 ? (
              <div className="empty-state compact">
                <Sparkles size={34} />
                <strong>{t("studioEmptyTitle")}</strong>
                <p>{t("studioEmptyBody")}</p>
              </div>
            ) : (
              latestJobs.map((job) => (
                <button className={activeJob?.id === job.id ? "job-card selected" : "job-card"} key={job.id} onClick={() => loadJob(job.id)}>
                  <span>{modeLabel(uiLanguage, job.resolved_mode ?? job.mode)}</span>
                  <strong>{statusLabel(uiLanguage, job.status)}</strong>
                  {job.error ? <small>{job.error}</small> : <small>{job.id}</small>}
                </button>
              ))
            )}
            <div className="artifact-list">
              {artifacts.map((a) => (
                <a className="artifact-link" href={`${API}/artifacts/${a.id}/download`} key={a.id}>
                  <span>{a.label}</span>
                  <small>{a.kind}</small>
                </a>
              ))}
            </div>
          </section>

          <section className="settings-box">
            <h2>{t("llmConfig")}</h2>
            <select value={catalog?.selected ?? ""} onChange={(e) => selectModel(e.target.value)}>
              {catalog?.options.map((o) => (
                <option key={o.selection} value={o.selection}>
                  {o.label}
                </option>
              ))}
            </select>
            <textarea
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              placeholder={t("pasteConfig")}
            />
            <div className="settings-actions">
              <button onClick={importConfig}>{t("importConfig")}</button>
              <a href={`${API}/settings/llm/export`} target="_blank">{t("exportConfig")}</a>
            </div>
            <div className="model-status">
              <strong>SenseNova U1</strong>
              <span>{snStatus?.model_dir ?? "models/Full"} · {snStatus?.safetensors ?? 0}/8</span>
              <span>{snStatus?.source_exists ? t("sourceReady") : t("sourceMissing")} · {snStatus?.source_dir ?? "../SenseNova-U1-main/src"}</span>
              {snStatus?.source_error ? <span>{snStatus.source_error}</span> : null}
              <a href={snStatus?.huggingface_url ?? "https://huggingface.co/sensenova/SenseNova-U1-8B-MoT"} target="_blank">{t("hfDownloadPage")}</a>
              <button onClick={downloadSenseNova}>{t("downloadModel")}</button>
              {downloadLog ? <pre>{downloadLog}</pre> : null}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function PaneHeader({ title, icon, trailing }: { title: string; icon?: React.ReactNode; trailing?: React.ReactNode }) {
  return (
    <div className="pane-head">
      <h2>{title}</h2>
      <span>{trailing ?? icon}</span>
    </div>
  );
}

function ChatMessage({
  message,
  job,
  events,
  artifacts,
  onOpenJob,
  t,
  language,
}: {
  message: Message;
  job?: Job;
  events: JobEvent[];
  artifacts: Artifact[];
  onOpenJob: (jobId: string) => void;
  t: TranslateFn;
  language: UiLanguage;
}) {
  const jobId = typeof message.metadata?.job_id === "string" ? String(message.metadata.job_id) : "";

  return (
    <div className={`message ${message.role}`}>
      <div className="message-stack">
        <div className="message-bubble">
          <p>{message.content}</p>
          {jobId ? (
            <button className="inline-job-link" onClick={() => onOpenJob(jobId)}>
              {t("relatedJob", { id: jobId })}
            </button>
          ) : null}
        </div>
        {jobId ? (
          <JobProgressBubble
            jobId={jobId}
            job={job}
            events={events}
            artifacts={artifacts}
            onOpenJob={onOpenJob}
            t={t}
            language={language}
          />
        ) : null}
      </div>
    </div>
  );
}

function JobProgressBubble({
  jobId,
  job,
  events,
  artifacts,
  onOpenJob,
  t,
  language,
}: {
  jobId: string;
  job?: Job;
  events: JobEvent[];
  artifacts: Artifact[];
  onOpenJob: (jobId: string) => void;
  t: TranslateFn;
  language: UiLanguage;
}) {
  const latestEvent = events[events.length - 1];
  const latestMessage = eventMessage(language, latestEvent, job);
  const status = job?.status ?? "running";
  const isTerminal = status === "completed" || status === "failed";

  return (
    <div className={`job-progress-bubble ${status}`}>
      <div className="job-progress-head">
        <span className="job-status-icon">
          {status === "completed" ? <CheckCircle2 size={18} /> : status === "failed" ? <CircleAlert size={18} /> : <span className="spinner" />}
        </span>
        <div>
          <strong>{t("jobTitle", { mode: modeLabel(language, job?.resolved_mode ?? job?.mode), status: statusLabel(language, status) })}</strong>
          <small>{jobId}</small>
        </div>
        <button onClick={() => onOpenJob(jobId)}>{t("open")}</button>
      </div>
      <div className="job-progress-current">{latestMessage}</div>
      {events.length ? (
        <ol className="job-event-list">
          {events.slice(-5).map((event) => (
            <li key={event.id}>
              <span>{eventLabel(language, event.type)}</span>
              <p>{eventMessage(language, event, job)}</p>
            </li>
          ))}
        </ol>
      ) : (
        <div className="job-waiting">{t("connectingEvents")}</div>
      )}
      {artifacts.length ? (
        <div className="job-artifacts">
          {artifacts.map((artifact) => (
            <a href={`${API}/artifacts/${artifact.id}/download`} key={artifact.id}>
              {artifact.label}
              <small>{artifact.kind}</small>
            </a>
          ))}
        </div>
      ) : null}
      {!isTerminal && latestEvent?.type === "progress" ? (
        <div className="job-progress-note">{t("localU1Note")}</div>
      ) : null}
    </div>
  );
}

type TranslateFn = (key: I18nKey, vars?: Record<string, string | number>) => string;

function eventMessage(language: UiLanguage, event?: JobEvent, job?: Job): string {
  const tx = (key: I18nKey, vars?: Record<string, string | number>) => translate(language, key, vars);
  if (!event) return job?.error || tx("noJobEvent");
  const payload = event.payload ?? {};
  if (typeof payload.message === "string" && payload.message) return localizeBackendMessage(language, payload.message);
  if (typeof payload.summary === "string" && payload.summary) return payload.summary;
  if (typeof payload.error === "string" && payload.error) return payload.error;
  if (event.type === "route" && typeof payload.mode === "string") return tx("routeMessage", { mode: modeLabel(language, payload.mode) });
  if (event.type === "artifact" && typeof payload.label === "string") return tx("artifactMessage", { label: payload.label });
  if (event.type === "exports") return tx("exportsMessage");
  if (event.type === "completed") return tx("completedMessage");
  if (event.type === "failed") return job?.error || tx("failedMessage");
  return eventLabel(language, event.type);
}

function localizeBackendMessage(language: UiLanguage, message: string): string {
  const tx = (key: I18nKey, vars?: Record<string, string | number>) => translate(language, key, vars);
  const text = String(message || "");
  if (text === "任务已启动") return tx("taskStarted");
  if (text === "正在整理上传资料") return tx("digestingSources");
  if (text === "正在规划完整海报") return tx("planningPoster");
  if (text === "SenseNova 正在生成完整大型海报") return tx("generatingPoster");
  if (text === "正在规划科研绘图/架构图") return tx("planningResearch");
  if (text === "SenseNova 正在生成完整科研图") return tx("generatingResearch");
  if (text === "正在生成图片二次编辑指令") return tx("planningEdit");
  if (text === "SenseNova 正在执行图片二次绘制") return tx("generatingEdit");
  let match = text.match(/^正在规划\s*(\d+)\s*页 PPT$/);
  if (match) return tx("planningPpt", { count: match[1] });
  match = text.match(/^正在生成第\s*(\d+)\/(\d+)\s*页 prompt$/);
  if (match) return tx("buildingPagePrompt", { page: match[1], total: match[2] });
  match = text.match(/^SenseNova 正在生成第\s*(\d+)\/(\d+)\s*页整图$/);
  if (match) return tx("generatingSlide", { page: match[1], total: match[2] });
  return text;
}

function eventLabel(language: UiLanguage, type: string): string {
  const keys: Record<string, I18nKey> = {
    status: "eventStatus",
    route: "eventRoute",
    digest: "eventDigest",
    progress: "eventProgress",
    artifact: "eventArtifact",
    exports: "eventExports",
    completed: "eventCompleted",
    failed: "eventFailed",
  };
  const key = keys[type];
  return key ? translate(language, key) : type;
}

function modeLabel(language: UiLanguage, mode?: string): string {
  const keys: Record<string, I18nKey> = {
    auto: "modeAuto",
    poster: "modePoster",
    research_figure: "modeResearch",
    edit: "modeEdit",
  };
  if (mode === "ppt") return "PPT";
  if (!mode) return translate(language, "modeGenerate");
  const key = keys[mode];
  return key ? translate(language, key) : mode;
}

function statusLabel(language: UiLanguage, status: string): string {
  const keys: Record<string, I18nKey> = {
    pending: "statusPending",
    running: "statusRunning",
    completed: "statusCompleted",
    failed: "statusFailed",
  };
  const key = keys[status];
  return key ? translate(language, key) : status;
}

function translate(language: UiLanguage, key: I18nKey, vars?: Record<string, string | number>): string {
  let text: string = i18n[language][key] ?? i18n.en[key] ?? key;
  if (vars) {
    Object.entries(vars).forEach(([name, value]) => {
      text = text.split(`{${name}}`).join(String(value));
    });
  }
  return text;
}

function detectInitialLanguage(): UiLanguage {
  const saved = localStorage.getItem("open_notebook_ui_language");
  if (isUiLanguage(saved)) return saved;
  const lang = navigator.language.toLowerCase();
  if (lang.startsWith("ja")) return "ja";
  if (lang.includes("tw") || lang.includes("hk") || lang.includes("mo") || lang.includes("hant")) return "zh-TW";
  if (lang.startsWith("zh")) return "zh-CN";
  return "en";
}

function isUiLanguage(value: unknown): value is UiLanguage {
  return value === "en" || value === "zh-CN" || value === "zh-TW" || value === "ja";
}

function isOutputLanguage(value: unknown): value is OutputLanguage {
  return value === "auto" || isUiLanguage(value);
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
