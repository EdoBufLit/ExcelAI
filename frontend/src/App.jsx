import { useEffect, useMemo, useState } from "react";
import {
  applyTransform,
  buildDownloadUrl,
  clarifyPlan,
  fetchUsage,
  generatePlan,
  previewTransform,
  uploadFile
} from "./api";
import PromptPresets from "./components/PromptPresets";
import transformPresets from "./config/transform-presets.json";
import { toUiErrorMessage } from "./utils/error-message";
import { buildHumanResultExplanation } from "./utils/result-explanation";

const USER_KEY = "excel_ai_transformer_user_id";
const EMPTY_PLAN_OPERATIONS_MESSAGE =
  "Il piano non contiene operazioni. Genera o modifica il piano prima di applicarlo.";

const STEPS = [
  { num: 1, label: "Carica" },
  { num: 2, label: "Descrivi" },
  { num: 3, label: "Rivedi" },
  { num: 4, label: "Scarica" }
];

function getUserId() {
  const existing = localStorage.getItem(USER_KEY);
  if (existing) return existing;
  const created = `user_${Math.random().toString(36).slice(2, 10)}`;
  localStorage.setItem(USER_KEY, created);
  return created;
}

function DataTable({ rows }) {
  if (!rows?.length) return <p className="muted">Nessun dato da mostrare.</p>;
  const columns = Object.keys(rows[0]);

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map((column) => (
                <td key={column}>{row[column] == null ? "" : String(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function parsePlanText(rawPlanText) {
  try {
    return { plan: JSON.parse(rawPlanText), isValidJson: true };
  } catch {
    return { plan: null, isValidJson: false };
  }
}

export default function App() {
  const [userId] = useState(getUserId);
  const [usage, setUsage] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadPayload, setUploadPayload] = useState(null);
  const [prompt, setPrompt] = useState("Pulisci gli spazi nelle colonne testo e ordina per importo crescente.");
  const [selectedPresetId, setSelectedPresetId] = useState(null);
  const [planText, setPlanText] = useState('{"operations":[]}');
  const [planWarnings, setPlanWarnings] = useState([]);
  const [clarify, setClarify] = useState(null);
  const [clarifyAnswer, setClarifyAnswer] = useState("");
  const [applyPayload, setApplyPayload] = useState(null);
  const [resultExplanation, setResultExplanation] = useState([]);
  const [previewPayload, setPreviewPayload] = useState(null);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [outputFormat, setOutputFormat] = useState("xlsx");
  const [loading, setLoading] = useState({
    usage: false,
    upload: false,
    plan: false,
    preview: false,
    apply: false
  });
  const [error, setError] = useState("");
  const [toastMessage, setToastMessage] = useState("");
  const [pipelineDebug, setPipelineDebug] = useState({
    uploadResult: null,
    analyzeResult: null,
    planResult: null,
    errors: []
  });

  const [activeTab, setActiveTab] = useState("prompt");
  const [showDebug, setShowDebug] = useState(false);

  function logPipelineError(stage, err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[pipeline] ${stage} error`, err);
    setPipelineDebug((previous) => ({
      ...previous,
      errors: [{ stage, message }, ...previous.errors].slice(0, 10)
    }));
    return message;
  }

  function applyPlanPayloadToState(payload) {
    setPipelineDebug((previous) => ({ ...previous, planResult: payload }));
    console.log("[pipeline] plan result", payload);

    if (payload?.type === "plan" && payload.plan && typeof payload.plan === "object") {
      setPlanText(JSON.stringify(payload.plan, null, 2));
      setPlanWarnings(payload.warnings || []);
      setClarify(null);
      setClarifyAnswer("");
      return;
    }

    if (payload?.type === "clarify") {
      setPlanText('{"operations":[]}');
      setPlanWarnings([]);
      setShowConfirmation(false);
      setPreviewPayload(null);
      setClarify({
        question: payload.question || "La richiesta non e ancora chiara.",
        choices: Array.isArray(payload.choices) ? payload.choices : [],
        clarifyId: payload.clarifyId
      });
      setClarifyAnswer("");
      return;
    }

    throw new Error("Risposta del planner non valida.");
  }

  function getExecutablePlanOrShowError({ closeConfirmation } = { closeConfirmation: false }) {
    if (clarify) {
      setError("Rispondi prima alla richiesta di chiarimento per ottenere un piano valido.");
      if (closeConfirmation) {
        setShowConfirmation(false);
      }
      return null;
    }

    const parsedPlanResult = parsePlanText(planText);
    if (!parsedPlanResult.isValidJson) {
      setError(toUiErrorMessage("invalid_plan_json"));
      if (closeConfirmation) {
        setShowConfirmation(false);
      }
      return null;
    }

    if (!Array.isArray(parsedPlanResult.plan?.operations) || parsedPlanResult.plan.operations.length === 0) {
      setError(EMPTY_PLAN_OPERATIONS_MESSAGE);
      if (closeConfirmation) {
        setShowConfirmation(false);
      }
      return null;
    }

    return parsedPlanResult.plan;
  }

  const hasPendingClarification = Boolean(clarify);
  const hasUploadedFile = Boolean(uploadPayload?.fileId);
  const hasNonEmptyPlan = useMemo(() => planText.trim().length > 0, [planText]);

  const planHasOperations = useMemo(() => {
    if (!hasNonEmptyPlan) return false;
    const parsedPlanResult = parsePlanText(planText);
    if (!parsedPlanResult.isValidJson) return false;
    return Array.isArray(parsedPlanResult.plan?.operations) && parsedPlanResult.plan.operations.length > 0;
  }, [planText, hasNonEmptyPlan]);

  const canOpenConfirmation = hasUploadedFile && hasNonEmptyPlan && planHasOperations && !hasPendingClarification;
  
  useEffect(() => {
    refreshUsage();
  }, []);

  useEffect(() => {
    if (!error) return;
    setToastMessage(error);
    const timer = setTimeout(() => setToastMessage(""), 4500);
    return () => clearTimeout(timer);
  }, [error]);

  useEffect(() => {
    if (planHasOperations && !clarify) {
      setActiveTab("plan");
    }
  }, [planHasOperations]);

  useEffect(() => {
    if (clarify) {
      setActiveTab("prompt");
    }
  }, [clarify]);

  async function refreshUsage() {
    setLoading((s) => ({ ...s, usage: true }));
    try {
      const usageData = await fetchUsage(userId);
      setUsage(usageData);
    } catch (err) {
      setError(logPipelineError("usage", err));
    } finally {
      setLoading((s) => ({ ...s, usage: false }));
    }
  }

  async function generatePlanForFile(fileId) {
    setLoading((s) => ({ ...s, plan: true }));
    try {
      const payload = await generatePlan({
        fileId,
        prompt,
        userId
      });
      applyPlanPayloadToState(payload);
      return payload;
    } catch (err) {
      setError(logPipelineError("plan", err));
      return null;
    } finally {
      setLoading((s) => ({ ...s, plan: false }));
    }
  }

  async function onUpload() {
    if (!selectedFile) return;
    setError("");
    setApplyPayload(null);
    setResultExplanation([]);
    setPreviewPayload(null);
    setShowConfirmation(false);
    setClarify(null);
    setClarifyAnswer("");
    setPlanWarnings([]);
    setPipelineDebug((previous) => ({
      ...previous,
      uploadResult: null,
      analyzeResult: null,
      planResult: null,
      errors: []
    }));
    setLoading((s) => ({ ...s, upload: true }));
    try {
      const payload = await uploadFile(selectedFile);
      if (!payload?.fileId || typeof payload.fileId !== "string") {
        throw new Error("Upload completato ma file_id mancante nella risposta API.");
      }
      console.log("[pipeline] upload result", payload);
      console.log("[pipeline] analyze result", payload.analysis);
      setPipelineDebug((previous) => ({
        ...previous,
        uploadResult: payload,
        analyzeResult: payload.analysis
      }));
      setUploadPayload(payload);
      setPlanText('{"operations":[]}');
      setActiveTab("prompt");
    } catch (err) {
      setError(logPipelineError("upload", err));
    } finally {
      setLoading((s) => ({ ...s, upload: false }));
    }
  }

  async function onGeneratePlan() {
    if (!uploadPayload?.fileId) return;
    setError("");
    setPreviewPayload(null);
    setShowConfirmation(false);
    setClarify(null);
    setClarifyAnswer("");
    await generatePlanForFile(uploadPayload.fileId);
  }

  async function onSubmitClarify(selectedAnswer) {
    if (!uploadPayload?.fileId || !clarify?.clarifyId) return;
    const answer = (selectedAnswer ?? clarifyAnswer).trim();
    if (!answer) {
      setError("Scrivi una risposta o seleziona una scelta prima di inviare.");
      return;
    }

    setError("");
    setLoading((s) => ({ ...s, plan: true }));
    try {
      const payload = await clarifyPlan({
        fileId: uploadPayload.fileId,
        prompt,
        clarifyId: clarify.clarifyId,
        answer
      });
      applyPlanPayloadToState(payload);
    } catch (err) {
      setError(logPipelineError("clarify", err));
    } finally {
      setLoading((s) => ({ ...s, plan: false }));
    }
  }

  async function onApply() {
    if (!uploadPayload?.fileId || !previewPayload?.previewAvailable || isLimitReached || clarify) return;
    setError("");
    const executablePlan = getExecutablePlanOrShowError();
    if (!executablePlan) {
      return;
    }
    setLoading((s) => ({ ...s, apply: true }));
    try {
      const payload = await applyTransform({
        fileId: uploadPayload.fileId,
        userId,
        plan: executablePlan,
        outputFormat
      });
      setApplyPayload(payload);
      setResultExplanation(buildHumanResultExplanation(executablePlan));
      setUsage((previous) => ({
        userId,
        usageCount: payload.usageCount,
        remainingUses: payload.remainingUses,
        limit: previous?.limit ?? 5
      }));
      await refreshUsage();
      setShowConfirmation(false);
    } catch (err) {
      setError(logPipelineError("apply", err));
    } finally {
      setLoading((s) => ({ ...s, apply: false }));
    }
  }

  async function onOpenConfirmation() {
    if (!uploadPayload?.fileId || clarify) return;
    setError("");
    const executablePlan = getExecutablePlanOrShowError({ closeConfirmation: true });
    if (!executablePlan) {
      return;
    }
    setShowConfirmation(true);
    setPreviewPayload(null);
    setLoading((s) => ({ ...s, preview: true }));
    try {
      const payload = await previewTransform({
        fileId: uploadPayload.fileId,
        plan: executablePlan
      });
      setPreviewPayload(payload);
    } catch (err) {
      setError(logPipelineError("preview", err));
    } finally {
      setLoading((s) => ({ ...s, preview: false }));
    }
  }

  function onCancelConfirmation() {
    setShowConfirmation(false);
  }

  function onPresetSelect(preset) {
    setPrompt(preset.prompt);
    setSelectedPresetId(preset.id);
    setShowConfirmation(false);
    setPreviewPayload(null);
    setClarify(null);
    setClarifyAnswer("");
  }

  const usageLabel = useMemo(() => {
    if (!usage) return "Caricamento...";
    return `${usage.remainingUses} / ${usage.limit} elaborazioni rimaste`;
  }, [usage]);

  const usagePillLabel = useMemo(() => {
    if (!usage) return "...";
    return `${usage.remainingUses} / ${usage.limit} elaborazioni`;
  }, [usage]);

  const isLimitReached = useMemo(() => {
    if (!usage) return false;
    return usage.remainingUses <= 0;
  }, [usage]);


  const currentStep = useMemo(() => {
    if (applyPayload?.analysis) return 4;
    if (planHasOperations && !hasPendingClarification) return 3;
    if (hasUploadedFile) return 2;
    return 1;
  }, [applyPayload, planHasOperations, hasPendingClarification, hasUploadedFile]);

  function onUpgradeClick() {
    setError("Limite free raggiunto. Passa al piano Pro (billing in arrivo).");
  }

  return (
    <main className="page">
      {/* ── Top Navigation ── */}
      <nav className="top-bar">
        <div className="top-bar-brand">
          <svg className="brand-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="3" y1="15" x2="21" y2="15" />
            <line x1="9" y1="3" x2="9" y2="21" />
          </svg>
          <span>Excel AI Transformer</span>
        </div>
        <div className="top-bar-right">
          <button className="usage-pill" onClick={refreshUsage} disabled={loading.usage} title="Clicca per aggiornare">
            {loading.usage ? (
              <span className="spinner" />
            ) : (
              <svg className="usage-pill-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            )}
            <span>{usagePillLabel}</span>
          </button>
          {isLimitReached && (
            <button className="btn-upgrade" onClick={onUpgradeClick}>
              Passa a Pro
            </button>
          )}
          <div className="user-avatar" title={`Account: ${userId}`}>
            {userId.slice(-2).toUpperCase()}
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="hero">
        <span className="hero-badge">AI-Powered</span>
        <h1>Trasforma i tuoi fogli di calcolo</h1>
        <p className="hero-subtitle">
          Descrivi le modifiche in linguaggio naturale. L'intelligenza artificiale si occupa del resto.
        </p>
      </section>

      {/* ── Stepper ── */}
      <div className="stepper">
        {STEPS.map((step) => (
          <div
            key={step.num}
            className={`stepper-step${currentStep === step.num ? " stepper-active" : ""}${currentStep > step.num ? " stepper-completed" : ""}`}
          >
            <div className="stepper-circle">
              {currentStep > step.num ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : (
                step.num
              )}
            </div>
            <span className="stepper-label">{step.label}</span>
          </div>
        ))}
      </div>

      {/* ── Step 1: Upload ── */}
      <section className={`card${currentStep === 1 ? " card-active" : ""}${currentStep > 1 ? " card-done" : ""}`}>
        <div className="card-header">
          <div className={`card-step-num${currentStep > 1 ? " card-step-done" : ""}`}>
            {currentStep > 1 ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              "1"
            )}
          </div>
          <div className="card-header-text">
            <h2>Carica il tuo file</h2>
            <p className="card-desc">Seleziona un file CSV o XLSX da trasformare</p>
          </div>
        </div>

        <label className="upload-zone" htmlFor="file-input">
          <input
            id="file-input"
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
            hidden
          />
          {selectedFile ? (
            <div className="upload-zone-selected">
              <svg className="upload-zone-file-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <div className="upload-zone-info">
                <span className="upload-zone-name">{selectedFile.name}</span>
                <span className="upload-zone-size">{(selectedFile.size / 1024).toFixed(1)} KB</span>
              </div>
              <span className="upload-zone-change">Cambia</span>
            </div>
          ) : (
            <div className="upload-zone-empty">
              <svg className="upload-zone-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span className="upload-zone-text">Clicca per selezionare un file</span>
              <span className="upload-zone-hint">Formati supportati: CSV, XLSX</span>
            </div>
          )}
        </label>

        <button onClick={onUpload} disabled={!selectedFile || loading.upload}>
          {loading.upload ? (
            <><span className="spinner" /> Caricamento in corso...</>
          ) : (
            "Carica e analizza"
          )}
        </button>

        {uploadPayload?.analysis && (
          <>
            <div className="analysis-summary">
              <span className="analysis-stat">{uploadPayload.analysis.rowCount} righe</span>
              <span className="analysis-divider" />
              <span className="analysis-stat">{uploadPayload.analysis.columnCount} colonne</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Colonna</th>
                    <th>Tipo</th>
                    <th>Valori nulli</th>
                    <th>Esempio</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadPayload.analysis.columns.map((column) => (
                    <tr key={column.name}>
                      <td><strong>{column.name}</strong></td>
                      <td><span className="badge-type">{column.dtype}</span></td>
                      <td>{column.nullCount}</td>
                      <td className="muted">{column.sampleValues.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>Anteprima dati</h3>
            <DataTable rows={uploadPayload.analysis.preview} />
          </>
        )}
      </section>

      {/* ── Step 2: Prompt & Plan ── */}
      <section className={`card${currentStep === 2 ? " card-active" : ""}${currentStep > 2 ? " card-done" : ""}`}>
        <div className="card-header">
          <div className={`card-step-num${currentStep > 2 ? " card-step-done" : ""}`}>
            {currentStep > 2 ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              "2"
            )}
          </div>
          <div className="card-header-text">
            <h2>Descrivi la trasformazione</h2>
            <p className="card-desc">Spiega cosa vuoi fare con i tuoi dati o scegli un preset</p>
          </div>
        </div>

        <div className="tab-bar">
          <button
            type="button"
            className={`tab${activeTab === "prompt" ? " tab-active" : ""}`}
            onClick={() => setActiveTab("prompt")}
          >
            Istruzioni
          </button>
          <button
            type="button"
            className={`tab${activeTab === "plan" ? " tab-active" : ""}`}
            onClick={() => setActiveTab("plan")}
          >
            Piano AI
            {planHasOperations && <span className="tab-dot" />}
          </button>
        </div>

        {activeTab === "prompt" && (
          <div className="tab-content">
            <PromptPresets presets={transformPresets} selectedPresetId={selectedPresetId} onSelect={onPresetSelect} />
            <label className="label" htmlFor="prompt">
              Cosa vuoi fare con i tuoi dati?
            </label>
            <textarea
              id="prompt"
              value={prompt}
              onChange={(event) => {
                const nextPrompt = event.target.value;
                setPrompt(nextPrompt);
                setClarify(null);
                setClarifyAnswer("");
                if (selectedPresetId) {
                  const activePreset = transformPresets.find((preset) => preset.id === selectedPresetId);
                  if (activePreset && activePreset.prompt !== nextPrompt) {
                    setSelectedPresetId(null);
                  }
                }
              }}
              rows={4}
              placeholder="Es: Pulisci gli spazi, rinomina le colonne, ordina per data..."
            />
            <button onClick={onGeneratePlan} disabled={!uploadPayload || loading.plan}>
              {loading.plan ? (
                <><span className="spinner" /> Generazione in corso...</>
              ) : (
                "Genera piano AI"
              )}
            </button>
          </div>
        )}

        {activeTab === "plan" && (
          <div className="tab-content">
            <div className="plan-editor-header">
              <label className="label" htmlFor="plan">
                Piano di trasformazione
              </label>
              <p className="plan-hint">
                Generato dall'AI in formato JSON. Puoi modificarlo manualmente se necessario.
              </p>
            </div>
            <textarea
              id="plan"
              className="mono plan-textarea"
              value={planText}
              onChange={(event) => {
                setPlanText(event.target.value);
                setShowConfirmation(false);
                setPreviewPayload(null);
              }}
              rows={14}
            />
            {planWarnings.length > 0 && (
              <div className="warnings">
                <p className="warnings-title">Avvisi</p>
                <ul className="warnings-list">
                  {planWarnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {clarify && (
          <div className="clarification-box">
            <p className="clarification-title">Abbiamo bisogno di un chiarimento</p>
            <p className="clarification-question">{clarify.question}</p>
            {clarify.choices.length > 0 && (
              <div className="clarify-choice-row">
                {clarify.choices.map((choice) => (
                  <button
                    key={choice}
                    className="clarify-choice"
                    type="button"
                    onClick={() => {
                      setClarifyAnswer(choice);
                      void onSubmitClarify(choice);
                    }}
                    disabled={loading.plan}
                  >
                    {choice}
                  </button>
                ))}
              </div>
            )}
            <label className="label" htmlFor="clarify-answer">
              Oppure scrivi la tua risposta
            </label>
            <textarea
              id="clarify-answer"
              value={clarifyAnswer}
              onChange={(event) => setClarifyAnswer(event.target.value)}
              rows={2}
              placeholder="Scrivi qui la tua risposta..."
            />
            <button type="button" onClick={() => void onSubmitClarify()} disabled={loading.plan || !clarifyAnswer.trim()}>
              {loading.plan ? (
                <><span className="spinner" /> Invio in corso...</>
              ) : (
                "Invia risposta"
              )}
            </button>
          </div>
        )}
      </section>

      {/* ── Step 3: Review & Confirm ── */}
      <section className={`card${currentStep === 3 ? " card-active" : ""}${currentStep > 3 ? " card-done" : ""}`}>
        <div className="card-header">
          <div className={`card-step-num${currentStep > 3 ? " card-step-done" : ""}`}>
            {currentStep > 3 ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              "3"
            )}
          </div>
          <div className="card-header-text">
            <h2>Rivedi e conferma</h2>
            <p className="card-desc">Verifica le modifiche prima di applicarle ai tuoi dati</p>
          </div>
        </div>

        {!planHasOperations && !hasPendingClarification && (
          <p className="state-note">{EMPTY_PLAN_OPERATIONS_MESSAGE}</p>
        )}

        {isLimitReached && (
          <div className="limit-block">
            <div>
              <p className="limit-title">Limite raggiunto</p>
              <p className="limit-desc">Hai esaurito le elaborazioni gratuite disponibili.</p>
            </div>
            <button className="btn-upgrade" onClick={onUpgradeClick}>
              Passa a Pro
            </button>
          </div>
        )}

        <div className="row">
          <div className="format-select">
            <label className="label" htmlFor="output-format">Formato output</label>
            <select id="output-format" value={outputFormat} onChange={(event) => setOutputFormat(event.target.value)}>
              <option value="xlsx">XLSX (Excel)</option>
              <option value="csv">CSV</option>
            </select>
          </div>
          <button
            onClick={onOpenConfirmation}
            disabled={!canOpenConfirmation || loading.preview || isLimitReached}
          >
            {loading.preview ? (
              <><span className="spinner" /> Preparazione anteprima...</>
            ) : (
              "Anteprima e conferma"
            )}
          </button>
        </div>

        {showConfirmation && (
          <div className="confirm-panel">
            <h3>Riepilogo trasformazioni</h3>

            {loading.preview && <p className="muted">Generazione anteprima del risultato in corso...</p>}

            {!loading.preview && previewPayload && (
              <>
                <p className="confirm-summary">{previewPayload.summary}</p>

                <p className="label">Colonne coinvolte</p>
                <div className="chip-list">
                  {previewPayload.impactedColumns.length === 0 && <span className="muted">Nessuna colonna rilevata.</span>}
                  {previewPayload.impactedColumns.map((column) => (
                    <span key={column} className="chip">
                      {column}
                    </span>
                  ))}
                </div>

                <p className="label">Operazioni previste</p>
                <ol className="step-list">
                  {previewPayload.steps.map((step, index) => (
                    <li key={`${step.title}-${index}`} className="step-item">
                      <div className="step-head">
                        <strong>{step.title}</strong>
                      </div>
                      <p className="muted">{step.description}</p>
                      <div className="chip-list">
                        {step.columns.map((column) => (
                          <span key={column} className="chip subtle">
                            {column}
                          </span>
                        ))}
                      </div>
                    </li>
                  ))}
                </ol>

                <p className="label">Anteprima risultato (max 10 righe)</p>
                <DataTable rows={previewPayload.analysis.preview} />

                {!previewPayload.previewAvailable && (
                  <p className="state-note">Anteprima non disponibile: l'applicazione e disabilitata.</p>
                )}

                <div className="row action-row">
                  <button className="ghost" onClick={onCancelConfirmation}>
                    Annulla
                  </button>
                  <button
                    onClick={onApply}
                    disabled={!previewPayload.previewAvailable || loading.apply || isLimitReached || hasPendingClarification}
                  >
                    {loading.apply ? (
                      <><span className="spinner" /> Applicazione in corso...</>
                    ) : (
                      "Applica trasformazioni"
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </section>

      {/* ── Step 4: Download ── */}
      <section className={`card${currentStep === 4 ? " card-active" : ""}`}>
        <div className="card-header">
          <div className="card-step-num">4</div>
          <div className="card-header-text">
            <h2>Scarica il risultato</h2>
            <p className="card-desc">Il file trasformato e pronto per il download</p>
          </div>
        </div>

        {applyPayload?.analysis ? (
          <>
            <div className="result-success">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>Trasformazione completata con successo</span>
            </div>
            <h3>Risultato in breve</h3>
            <ul className="human-summary">
              {resultExplanation.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <a className="download-btn" href={buildDownloadUrl(applyPayload.resultId)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Scarica file trasformato
            </a>
            <h3>Anteprima output</h3>
            <DataTable rows={applyPayload.analysis.preview} />
          </>
        ) : (
          <p className="muted">Nessun risultato disponibile. Completa i passaggi precedenti per generare l'output.</p>
        )}
      </section>

      {/* ── Debug (Collapsible) ── */}
      <section className="card debug-section">
        <button className="debug-toggle" type="button" onClick={() => setShowDebug(!showDebug)}>
          <span>Dettagli tecnici</span>
          <svg
            className={`debug-chevron${showDebug ? " rotated" : ""}`}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        {showDebug && (
          <div className="debug-content">
            <p className="label">Upload result</p>
            <pre className="mono debug-pre">{pipelineDebug.uploadResult ? JSON.stringify(pipelineDebug.uploadResult, null, 2) : "Nessun dato."}</pre>
            <p className="label">Analyze result</p>
            <pre className="mono debug-pre">{pipelineDebug.analyzeResult ? JSON.stringify(pipelineDebug.analyzeResult, null, 2) : "Nessun dato."}</pre>
            <p className="label">Plan result</p>
            <pre className="mono debug-pre">{pipelineDebug.planResult ? JSON.stringify(pipelineDebug.planResult, null, 2) : "Nessun dato."}</pre>
            <p className="label">Errori recenti</p>
            {pipelineDebug.errors.length === 0 ? (
              <p className="muted">Nessun errore registrato.</p>
            ) : (
              <ul className="warnings">
                {pipelineDebug.errors.map((item, idx) => (
                  <li key={`${item.stage}-${idx}`}>
                    [{item.stage}] {item.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* ── Error & Toast ── */}
      {error && (
        <section className="card error-card">
          <strong>Errore:</strong> {error}
        </section>
      )}
      {toastMessage && <div className="toast">{toastMessage}</div>}
    </main>
  );
}
