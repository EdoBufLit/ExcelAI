import { useEffect, useMemo, useState } from "react";
import {
  applyTransform,
  buildDownloadUrl,
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
  const [needsClarification, setNeedsClarification] = useState(false);
  const [clarificationQuestion, setClarificationQuestion] = useState("");
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
  const [pipelineDebug, setPipelineDebug] = useState({
    uploadResult: null,
    analyzeResult: null,
    planResult: null,
    errors: []
  });

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
    setPlanText(JSON.stringify(payload.plan, null, 2));
    setPlanWarnings(payload.warnings || []);
    setNeedsClarification(Boolean(payload.needsClarification));
    setClarificationQuestion(payload.clarificationQuestion || "");
    setPipelineDebug((previous) => ({ ...previous, planResult: payload }));
    console.log("[pipeline] plan result", payload);
  }

  function getExecutablePlanOrShowError({ closeConfirmation } = { closeConfirmation: false }) {
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

  useEffect(() => {
    refreshUsage();
  }, []);

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
    setNeedsClarification(false);
    setClarificationQuestion("");
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
      await generatePlanForFile(payload.fileId);
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
    setNeedsClarification(false);
    setClarificationQuestion("");
    await generatePlanForFile(uploadPayload.fileId);
  }

  async function onApply() {
    if (!uploadPayload?.fileId || !previewPayload?.previewAvailable || isLimitReached || needsClarification) return;
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
    if (!uploadPayload?.fileId || needsClarification) return;
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
    setNeedsClarification(false);
    setClarificationQuestion("");
  }

  const usageLabel = useMemo(() => {
    if (!usage) return "Caricamento utilizzi...";
    return `${usage.remainingUses} / ${usage.limit} elaborazioni rimaste`;
  }, [usage]);

  const isLimitReached = useMemo(() => {
    if (!usage) return false;
    return usage.remainingUses <= 0;
  }, [usage]);

  const hasUploadedFile = Boolean(uploadPayload?.fileId);
  const hasNonEmptyPlan = useMemo(() => planText.trim().length > 0, [planText]);

  const planHasOperations = useMemo(() => {
    if (!hasNonEmptyPlan) return false;
    const parsedPlanResult = parsePlanText(planText);
    if (!parsedPlanResult.isValidJson) return false;
    return Array.isArray(parsedPlanResult.plan?.operations) && parsedPlanResult.plan.operations.length > 0;
  }, [planText, hasNonEmptyPlan]);

  const canOpenConfirmation = hasUploadedFile && hasNonEmptyPlan && planHasOperations;

  function onUpgradeClick() {
    setError("Limite free raggiunto. Passa al piano Pro (billing in arrivo).");
  }

  return (
    <main className="page">
      <div className={`usage-sticky ${isLimitReached ? "limit" : ""}`}>
        <span className="usage-text">{loading.usage ? "..." : usageLabel}</span>
        {isLimitReached && (
          <button className="pro-cta" onClick={onUpgradeClick}>
            Passa al piano Pro
          </button>
        )}
      </div>

      <section className="hero">
        <p className="eyebrow">MVP</p>
        <h1>Excel AI Transformer</h1>
        <p className="subtitle">Trasforma file CSV/XLSX con piano JSON generato da LLM e applicazione sicura.</p>
        <div className="badge-row">
          <span className="badge mono">user_id: {userId}</span>
          <span className={`badge ${isLimitReached ? "badge-limit" : ""}`}>{loading.usage ? "..." : usageLabel}</span>
          <button className="secondary" onClick={refreshUsage} disabled={loading.usage}>
            Aggiorna uso
          </button>
        </div>
      </section>

      <section className="card">
        <h2>1) Upload File</h2>
        <div className="row">
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
          />
          <button onClick={onUpload} disabled={!selectedFile || loading.upload}>
            {loading.upload ? "Caricamento..." : "Upload e Analizza"}
          </button>
        </div>
        {uploadPayload?.analysis && (
          <>
            <p className="muted">
              Righe: {uploadPayload.analysis.rowCount} | Colonne: {uploadPayload.analysis.columnCount}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Colonna</th>
                    <th>Tipo</th>
                    <th>Null</th>
                    <th>Sample</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadPayload.analysis.columns.map((column) => (
                    <tr key={column.name}>
                      <td>{column.name}</td>
                      <td>{column.dtype}</td>
                      <td>{column.nullCount}</td>
                      <td>{column.sampleValues.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>Preview Input</h3>
            <DataTable rows={uploadPayload.analysis.preview} />
          </>
        )}
      </section>

      <section className="card">
        <h2>2) Prompt e Piano AI</h2>
        <PromptPresets presets={transformPresets} selectedPresetId={selectedPresetId} onSelect={onPresetSelect} />
        <label className="label" htmlFor="prompt">
          Prompt
        </label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(event) => {
            const nextPrompt = event.target.value;
            setPrompt(nextPrompt);
            setNeedsClarification(false);
            setClarificationQuestion("");
            if (selectedPresetId) {
              const activePreset = transformPresets.find((preset) => preset.id === selectedPresetId);
              if (activePreset && activePreset.prompt !== nextPrompt) {
                setSelectedPresetId(null);
              }
            }
          }}
          rows={4}
        />
        <div className="row">
          <button onClick={onGeneratePlan} disabled={!uploadPayload || loading.plan}>
            {loading.plan ? "Generazione..." : "Genera Piano"}
          </button>
        </div>
        <label className="label" htmlFor="plan">
          Piano JSON (modificabile)
        </label>
        <textarea
          id="plan"
          className="mono"
          value={planText}
          onChange={(event) => {
            setPlanText(event.target.value);
            setShowConfirmation(false);
            setPreviewPayload(null);
          }}
          rows={12}
        />
        {planWarnings.length > 0 && (
          <ul className="warnings">
            {planWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
        {needsClarification && (
          <div className="clarification-box">
            <p className="clarification-title">Richiesta chiarimento</p>
            <p className="clarification-question">{clarificationQuestion}</p>
            <p className="muted">Aggiorna il prompt e premi "Genera Piano". Nessuna esecuzione verra avviata finche non chiarisci.</p>
          </div>
        )}
      </section>

      <section className="card">
        <h2>3) Conferma Prima Dell'applicazione</h2>
        {!planHasOperations && <p className="state-note">{EMPTY_PLAN_OPERATIONS_MESSAGE}</p>}
        {isLimitReached && (
          <div className="limit-block">
            <p className="limit-text">Hai raggiunto il limite di utilizzi gratuiti. L'esecuzione e bloccata.</p>
            <button className="pro-cta" onClick={onUpgradeClick}>
              Passa al piano Pro
            </button>
          </div>
        )}
        <div className="row">
          <select value={outputFormat} onChange={(event) => setOutputFormat(event.target.value)}>
            <option value="xlsx">XLSX</option>
            <option value="csv">CSV</option>
          </select>
          <button
            onClick={onOpenConfirmation}
            disabled={!canOpenConfirmation || loading.preview || isLimitReached || needsClarification}
          >
            {loading.preview ? "Preparazione preview..." : "Apri Conferma"}
          </button>
        </div>

        {showConfirmation && (
          <div className="confirm-panel">
            <h3>Conferma Trasformazioni</h3>

            {loading.preview && <p className="muted">Genero anteprima del risultato...</p>}

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

                <p className="label">Step previsti</p>
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

                <p className="label">Preview risultato (max 10 righe)</p>
                <DataTable rows={previewPayload.analysis.preview} />

                {!previewPayload.previewAvailable && (
                  <p className="state-note">Preview non disponibile: applicazione disabilitata.</p>
                )}

                <div className="row action-row">
                  <button className="ghost" onClick={onCancelConfirmation}>
                    Annulla
                  </button>
                  <button
                    className="danger"
                    onClick={onApply}
                    disabled={!previewPayload.previewAvailable || loading.apply || isLimitReached || needsClarification}
                  >
                    {loading.apply ? "Applicazione..." : "Applica trasformazioni"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2>4) Download Risultato</h2>
        {applyPayload?.analysis ? (
          <>
            <p className="muted">Output pronto. Uso residuo: {applyPayload.remainingUses}</p>
            <h3>Risultato in parole semplici</h3>
            <ul className="human-summary">
              {resultExplanation.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <a className="download" href={buildDownloadUrl(applyPayload.resultId)}>
              Scarica file trasformato
            </a>
            <h3>Preview Output</h3>
            <DataTable rows={applyPayload.analysis.preview} />
          </>
        ) : (
          <p className="muted">Nessun output disponibile. Completa la conferma per applicare il piano.</p>
        )}
      </section>

      <section className="card">
        <h2>Debug Pipeline</h2>
        <p className="muted">Upload, analisi, piano ed errori recenti.</p>
        <p className="label">Upload result</p>
        <pre className="mono">{pipelineDebug.uploadResult ? JSON.stringify(pipelineDebug.uploadResult, null, 2) : "Nessun dato."}</pre>
        <p className="label">Analyze result</p>
        <pre className="mono">{pipelineDebug.analyzeResult ? JSON.stringify(pipelineDebug.analyzeResult, null, 2) : "Nessun dato."}</pre>
        <p className="label">Plan result</p>
        <pre className="mono">{pipelineDebug.planResult ? JSON.stringify(pipelineDebug.planResult, null, 2) : "Nessun dato."}</pre>
        <p className="label">Errori</p>
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
      </section>

      {error && (
        <section className="card error">
          <strong>Errore:</strong> {error}
        </section>
      )}
    </main>
  );
}
