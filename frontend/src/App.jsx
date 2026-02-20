import { useEffect, useMemo, useState } from "react";
import Plot from "react-plotly.js";
import {
  csvExportUrl,
  getPageDetail,
  getPages,
  getSessions,
  getSummary,
  jsonExportUrl
} from "./api";
import { compactUrl, parseQueryState, scoreColor, writeQueryState } from "./utils";

const STATUS_OPTIONS = ["complete", "partial", "failed"];
const TONES = {
  good: "#2fb391",
  warn: "#d49b3d",
  bad: "#cc4f69",
  accent: "#6f9b4f"
};
const DIMENSION_LABELS = {
  onpage_seo: "On-Page SEO",
  schema_analysis: "Schema",
  content_analysis: "Content",
  link_analysis: "Links",
  performance: "Performance",
  readability: "Readability",
  security: "Security",
  accessibility: "Accessibility",
  canonical_analysis: "Canonical"
};
const DIMENSION_ORDER = [
  "onpage_seo",
  "schema_analysis",
  "content_analysis",
  "link_analysis",
  "performance",
  "readability",
  "security",
  "accessibility",
  "canonical_analysis"
];

function Hero({ summary, pagesCount, failedCount, highIssues }) {
  return (
    <section className="hero">
      <div className="hero-left">
        <h1>AI SEO Audit Command Center</h1>
        <p>Custom command center with responsive diagnostics and API-backed drilldown.</p>
        <div className="hero-stats">
          <KpiCard label="Site Grade" value={summary?.overall_grade ?? "F"} tone={scoreColor(summary?.overall_score ?? 0)} />
          <KpiCard label="Overall Score" value={`${summary?.overall_score ?? 0}`} tone={scoreColor(summary?.overall_score ?? 0)} />
          <KpiCard label="Pages" value={`${pagesCount}`} />
          <KpiCard label="Failed" value={`${failedCount}`} tone={TONES.bad} />
          <KpiCard label="High Issues" value={`${highIssues}`} tone={TONES.warn} />
        </div>
      </div>
      <div className="hero-ring" aria-label="Overall score ring">
        <div
          className="ring"
          style={{
            background: `conic-gradient(${scoreColor(summary?.overall_score ?? 0)} ${Math.max(
              0,
              Math.min(100, summary?.overall_score ?? 0)
            )}%, rgba(255,255,255,.13) 0)`
          }}
        >
          <div className="ring-inner">
            <strong>{summary?.overall_grade ?? "F"}</strong>
            <span>{summary?.overall_score ?? 0}/100</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function KpiCard({ label, value, tone }) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color: tone || "var(--ink)" }}>
        {value}
      </div>
    </div>
  );
}

function Skyline({ pages }) {
  const bars = pages.slice(0, 50).sort((a, b) => a.overall_score - b.overall_score);
  const maxBars = Math.max(1, bars.length);
  return (
    <section className="panel">
      <div className="panel-title">Score Skyline</div>
      <div className="skyline" role="img" aria-label="Skyline distribution of page scores">
        {bars.map((item, idx) => (
          <div
            key={item.page_id}
            className="skyline-bar"
            style={{
              height: `${Math.max(8, item.overall_score)}%`,
              width: `calc((100% - ${(maxBars - 1) * 2}px) / ${maxBars})`,
              background: scoreColor(item.overall_score)
            }}
            title={`${item.url}\nScore: ${item.overall_score}\nRisk: ${item.risk_index}`}
          />
        ))}
      </div>
    </section>
  );
}

function ActionQueue({ pages }) {
  const top = pages.slice().sort((a, b) => b.risk_index - a.risk_index).slice(0, 6);
  return (
    <section className="panel">
      <div className="panel-title">Action Queue</div>
      <div className="queue-grid">
        {top.map((p) => (
          <article key={p.page_id} className="queue-card">
            <h4 title={p.url}>{compactUrl(p.url, 68)}</h4>
            <div className="queue-row">
              <span>Risk</span>
              <strong>{p.risk_index.toFixed(1)}</strong>
            </div>
            <div className="queue-row">
              <span>Score</span>
              <strong style={{ color: scoreColor(p.overall_score) }}>{p.overall_score.toFixed(1)}</strong>
            </div>
            <div className="queue-row">
              <span>Issues</span>
              <strong>{p.issues_count}</strong>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [sessions, setSessions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [pages, setPages] = useState([]);
  const [pageDetail, setPageDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const initialQuery = useMemo(() => parseQueryState(), []);
  const [session, setSession] = useState(initialQuery.session);
  const [q, setQ] = useState(initialQuery.q);
  const [scoreMin, setScoreMin] = useState(initialQuery.scoreMin);
  const [scoreMax, setScoreMax] = useState(initialQuery.scoreMax);
  const [issuesMin, setIssuesMin] = useState(initialQuery.issuesMin);
  const [status, setStatus] = useState(initialQuery.status.length ? initialQuery.status : STATUS_OPTIONS);
  const [pageId, setPageId] = useState(initialQuery.pageId);

  const filterParams = useMemo(
    () => ({
      q,
      score_min: scoreMin,
      score_max: scoreMax,
      issues_min: issuesMin,
      status
    }),
    [q, scoreMin, scoreMax, issuesMin, status]
  );

  useEffect(() => {
    writeQueryState({ session, q, scoreMin, scoreMax, issuesMin, status, pageId });
  }, [session, q, scoreMin, scoreMax, issuesMin, status, pageId]);

  useEffect(() => {
    let mounted = true;
    getSessions()
      .then((data) => {
        if (!mounted) return;
        setSessions(data);
        if (!session && data.length) setSession(data[0].id);
      })
      .catch((err) => setError(`Failed to load sessions. ${err?.message || ""}`.trim()));
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    setLoading(true);
    setError("");
    Promise.all([getSummary(session), getPages(session, { ...filterParams, limit: 500, offset: 0 })])
      .then(([summaryData, pagesData]) => {
        setSummary(summaryData);
        setPages(pagesData.items ?? []);
        if (!pageId && pagesData.items?.length) setPageId(pagesData.items[0].page_id);
      })
      .catch((err) => setError(`Failed to load summary/pages. ${err?.message || ""}`.trim()))
      .finally(() => setLoading(false));
  }, [session, filterParams]);

  useEffect(() => {
    if (!session || !pageId) return;
    getPageDetail(session, pageId)
      .then(setPageDetail)
      .catch(() => setPageDetail(null));
  }, [session, pageId]);

  const failedCount = pages.filter((p) => p.audit_status === "failed").length;
  const highIssues = summary?.severity_distribution?.high ?? 0;

  const dimensionAverages = useMemo(() => {
    if (!summary?.dimension_averages) return [];
    const entries = summary.dimension_averages;
    return DIMENSION_ORDER.filter((key) => key in entries).map((key) => ({
      key,
      label: DIMENSION_LABELS[key] ?? key,
      value: Number(entries[key] ?? 0)
    }));
  }, [summary]);

  const heatmapRows = pages.slice(0, 12);
  const heatmapY = heatmapRows.map((_, idx) => `P${String(idx + 1).padStart(2, "0")}`);
  const heatmapX = ["On-Page", "Schema", "Content", "Links", "Perf", "Read", "Sec", "A11y"];
  const heatmapZ = heatmapRows.map((p) => [
    p.onpage_seo_score,
    p.schema_score,
    p.content_score,
    p.link_score,
    p.performance_score,
    p.readability_score,
    p.security_score,
    p.accessibility_score
  ]);

  const riskScatter = {
    x: pages.map((p) => p.overall_score),
    y: pages.map((p) => p.issues_count),
    text: pages.map((p) => compactUrl(p.url, 80)),
    marker: {
      size: pages.map((p) => Math.max(10, p.risk_index * 0.4)),
      color: pages.map((p) =>
        p.audit_status === "complete" ? TONES.good : p.audit_status === "partial" ? TONES.warn : TONES.bad
      )
    },
    mode: "markers",
    type: "scatter",
    hovertemplate: "%{text}<br>Score %{x:.1f}<br>Issues %{y}<extra></extra>"
  };

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Filters">
        <h2>Filters</h2>
        <label>
          Session
          <select value={session} onChange={(e) => setSession(e.target.value)} aria-label="Session">
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          URL contains
          <input value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label>
          Score min
          <input type="number" min={0} max={100} value={scoreMin} onChange={(e) => setScoreMin(Number(e.target.value))} />
        </label>
        <label>
          Score max
          <input type="number" min={0} max={100} value={scoreMax} onChange={(e) => setScoreMax(Number(e.target.value))} />
        </label>
        <label>
          Min issues
          <input type="number" min={0} value={issuesMin} onChange={(e) => setIssuesMin(Number(e.target.value))} />
        </label>
        <fieldset>
          <legend>Status</legend>
          {STATUS_OPTIONS.map((opt) => (
            <label key={opt} className="checkbox">
              <input
                type="checkbox"
                checked={status.includes(opt)}
                onChange={(e) => {
                  if (e.target.checked) setStatus((prev) => [...prev, opt]);
                  else setStatus((prev) => prev.filter((p) => p !== opt));
                }}
              />
              {opt}
            </label>
          ))}
        </fieldset>
        <a className="export-btn" href={csvExportUrl(session, filterParams)}>
          Download CSV
        </a>
        <a className="export-btn" href={jsonExportUrl(session, filterParams)}>
          Download JSON
        </a>
      </aside>

      <main className="main">
        {loading && <div className="notice">Loading dashboard...</div>}
        {error && <div className="notice error">{error}</div>}
        {!loading && !error && (
          <>
            <Hero summary={summary} pagesCount={pages.length} failedCount={failedCount} highIssues={highIssues} />

            <section className="dimension-strip">
              {dimensionAverages.map((dim) => (
                <article key={dim.key} className="dim-card">
                  <h4>{dim.label}</h4>
                  <div className="score" style={{ color: scoreColor(dim.value) }}>
                    {dim.value.toFixed(1)}
                  </div>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${Math.max(0, Math.min(100, dim.value))}%` }} />
                  </div>
                </article>
              ))}
            </section>

            <section className="panel-grid">
              <section className="panel panel-large">
                <div className="panel-title">Risk Map</div>
                <Plot
                  data={[riskScatter]}
                  layout={{
                    autosize: true,
                    paper_bgcolor: "rgba(0,0,0,0)",
                    plot_bgcolor: "rgba(0,0,0,0)",
                    margin: { t: 20, r: 15, l: 40, b: 40 },
                    xaxis: { title: "Overall score", gridcolor: "rgba(255,255,255,.08)" },
                    yaxis: { title: "Issue count", gridcolor: "rgba(255,255,255,.08)" }
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  className="plot"
                  useResizeHandler
                />
              </section>

              <section className="panel">
                <div className="panel-title">Dimension Heatmap</div>
                <Plot
                  data={[
                    {
                      type: "heatmap",
                      x: heatmapX,
                      y: heatmapY,
                      z: heatmapZ,
                      text: heatmapZ,
                      texttemplate: "%{text:.0f}",
                      colorscale: [
                        [0, "#7a3d49"],
                        [0.5, "#b48a4a"],
                        [1, "#3c8f74"]
                      ],
                      zmin: 0,
                      zmax: 100,
                      hovertemplate: "%{y} | %{x}: %{z:.0f}<extra></extra>"
                    }
                  ]}
                  layout={{
                    autosize: true,
                    paper_bgcolor: "rgba(0,0,0,0)",
                    plot_bgcolor: "rgba(0,0,0,0)",
                    margin: { t: 20, r: 15, l: 30, b: 20 }
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  className="plot"
                  useResizeHandler
                />
              </section>
            </section>

            <Skyline pages={pages} />

            <section className="panel">
              <div className="panel-title">Issue Pressure Matrix</div>
              <Plot
                data={[
                  {
                    x: ["High", "Medium", "Low"],
                    y: [
                      summary?.severity_distribution?.high ?? 0,
                      summary?.severity_distribution?.medium ?? 0,
                      summary?.severity_distribution?.low ?? 0
                    ],
                    type: "bar",
                    marker: { color: [TONES.bad, TONES.warn, TONES.accent] }
                  }
                ]}
                layout={{
                  autosize: true,
                  paper_bgcolor: "rgba(0,0,0,0)",
                  plot_bgcolor: "rgba(0,0,0,0)",
                  margin: { t: 20, r: 15, l: 30, b: 40 }
                }}
                config={{ displayModeBar: false, responsive: true }}
                className="plot short-plot"
                useResizeHandler
              />
            </section>

            <ActionQueue pages={pages} />

            <section className="panel-grid">
              <section className="panel panel-large">
                <div className="panel-title">Page Cockpit</div>
                <label className="inline-label">
                  Focus page
                  <select value={pageId} onChange={(e) => setPageId(e.target.value)}>
                    {pages.map((p) => (
                      <option key={p.page_id} value={p.page_id}>
                        {compactUrl(p.url, 90)}
                      </option>
                    ))}
                  </select>
                </label>
                {pageDetail && (
                  <>
                    <Plot
                      data={[
                        {
                          type: "scatterpolar",
                          r: [
                            pageDetail.summary.onpage_seo_score,
                            pageDetail.summary.schema_score,
                            pageDetail.summary.content_score,
                            pageDetail.summary.link_score,
                            pageDetail.summary.performance_score,
                            pageDetail.summary.readability_score,
                            pageDetail.summary.security_score,
                            pageDetail.summary.accessibility_score,
                            pageDetail.summary.onpage_seo_score
                          ],
                          theta: ["On-Page", "Schema", "Content", "Links", "Perf", "Read", "Sec", "A11y", "On-Page"],
                          fill: "toself",
                          line: { color: TONES.accent }
                        }
                      ]}
                      layout={{
                        autosize: true,
                        paper_bgcolor: "rgba(0,0,0,0)",
                        polar: { radialaxis: { range: [0, 100] } },
                        margin: { t: 10, r: 10, l: 10, b: 10 }
                      }}
                      config={{ displayModeBar: false, responsive: true }}
                      className="plot"
                      useResizeHandler
                    />
                    <div className="issue-list">
                      {(pageDetail.raw_data?.onpage_seo?.issues || [])
                        .concat(pageDetail.raw_data?.content_analysis?.issues || [])
                        .concat(pageDetail.raw_data?.link_analysis?.issues || [])
                        .slice(0, 8)
                        .map((issue, i) => (
                          <article key={`${issue.description}-${i}`} className={`issue issue-${issue.severity || "medium"}`}>
                            <strong>{issue.severity?.toUpperCase() || "MEDIUM"}</strong>
                            <p>{issue.description}</p>
                            <small>{issue.suggested_fix}</small>
                          </article>
                        ))}
                    </div>
                  </>
                )}
              </section>

              <section className="panel">
                <div className="panel-title">Top Issues</div>
                <ul className="top-issues">
                  {(summary?.top_issues || []).slice(0, 8).map((issue) => {
                    const severity = (issue.severity || "medium").toLowerCase();
                    return (
                      <li key={`${issue.description}-${issue.severity}`} className={`top-issue top-${severity}`}>
                        <div className="top-issue-head">
                          <span className={`sev-badge sev-${severity}`}>{severity.toUpperCase()}</span>
                          <span className="issue-count">{issue.count}</span>
                        </div>
                        <p title={issue.description}>{issue.description}</p>
                      </li>
                    );
                  })}
                  {!(summary?.top_issues || []).length && <li className="top-issue-empty">No issues found.</li>}
                </ul>
              </section>
            </section>

            <section className="panel">
              <div className="panel-title">Filtered Pages</div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>URL</th>
                      <th>Status</th>
                      <th>Overall</th>
                      <th>Risk</th>
                      <th>Issues</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pages.map((p) => (
                      <tr key={p.page_id} onClick={() => setPageId(p.page_id)} tabIndex={0}>
                        <td title={p.url}>{compactUrl(p.url, 72)}</td>
                        <td>{p.audit_status}</td>
                        <td style={{ color: scoreColor(p.overall_score) }}>{p.overall_score.toFixed(1)}</td>
                        <td>{p.risk_index.toFixed(1)}</td>
                        <td>{p.issues_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
