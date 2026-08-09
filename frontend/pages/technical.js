import Head from 'next/head';
import Link from 'next/link';
import styles from '../styles/Landing.module.css';

function ArchitectureDiagram() {
  return (
    <figure className={styles.diagramFigure}>
      <div className={styles.diagramScroll}>
        <svg
          viewBox="0 0 680 260"
          role="img"
          aria-label="Frontend talks directly to Supabase for reads and for writes that need no server-side compute, under Row Level Security. The backend is only in the loop for writes that need compute: generating a feed's embedding, or running the ask-a-question agent. It reads evidence back from Supabase and calls the Groq LLM to classify and reason, writing results back to Supabase."
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
            </marker>
          </defs>
          <g fontFamily="var(--mono)" fontSize="11" fill="currentColor">
            <rect x="20" y="30" width="150" height="56" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="95" y="54" textAnchor="middle">Frontend</text>
            <text x="95" y="70" textAnchor="middle" fontSize="9" opacity="0.65">Next.js · Azure SWA</text>

            <rect x="265" y="150" width="170" height="70" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <text x="350" y="177" textAnchor="middle">Supabase</text>
            <text x="350" y="193" textAnchor="middle" fontSize="9" opacity="0.65">Postgres + pgvector</text>
            <text x="350" y="206" textAnchor="middle" fontSize="9" opacity="0.65">Auth · RLS-enforced</text>

            <rect x="510" y="30" width="150" height="56" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="585" y="54" textAnchor="middle">Backend</text>
            <text x="585" y="70" textAnchor="middle" fontSize="9" opacity="0.65">FastAPI · Container Apps</text>

            <rect x="510" y="150" width="150" height="56" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="585" y="174" textAnchor="middle">Groq LLM</text>
            <text x="585" y="190" textAnchor="middle" fontSize="9" opacity="0.65">Llama 3.3 70B</text>

            <path d="M110 86 L280 150" stroke="currentColor" strokeWidth="1.8" fill="none" markerEnd="url(#arrow)" markerStart="url(#arrow)" />
            <text x="118" y="120" fontSize="9.5">reads / writes</text>
            <text x="118" y="132" fontSize="9.5">(RLS-enforced)</text>

            <path d="M170 55 L510 55" stroke="currentColor" strokeWidth="1.2" fill="none" strokeDasharray="3 4" markerEnd="url(#arrow)" />
            <text x="255" y="46" fontSize="9.5" fill="var(--accent)">new/edit feed · ask a question</text>

            <path d="M560 86 L420 150" stroke="currentColor" strokeWidth="1.4" fill="none" markerEnd="url(#arrow)" markerStart="url(#arrow)" />
            <text x="428" y="112" fontSize="9.5">retrieve evidence /</text>
            <text x="428" y="124" fontSize="9.5">write embeddings + results</text>

            <path d="M585 86 L585 150" stroke="currentColor" strokeWidth="1.4" fill="none" markerEnd="url(#arrow)" markerStart="url(#arrow)" />
            <text x="592" y="122" fontSize="9.5">classify / reason</text>
          </g>
        </svg>
      </div>
      <figcaption>
        Plain reads and writes (listing feeds, viewing evidence, editing a watchlist) go straight from the
        frontend to Supabase under RLS. The backend is only in the loop for the two writes that need real
        compute — creating or editing a feed (needs an embedding) and asking a question (runs the full agent).
      </figcaption>
    </figure>
  );
}

function OrchestrationDiagram() {
  return (
    <figure className={styles.diagramFigure}>
      <div className={styles.diagramScroll}>
        <svg
          viewBox="0 0 680 224"
          role="img"
          aria-label="Requests are classified by shape first. Router/dispatch handles a plain news lookup on its own, formatting a list with no LLM synthesis. ReAct and Plan-Execute both gather evidence differently but converge on one shared synthesize_insight function."
        >
          <defs>
            <marker id="arrow2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
            </marker>
          </defs>
          <g fontFamily="var(--mono)" fontSize="11" fill="currentColor">
            <rect x="10" y="14" width="190" height="58" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="105" y="36" textAnchor="middle">Router / dispatch</text>
            <text x="105" y="52" textAnchor="middle" fontSize="9" opacity="0.65">known shape → news lookup</text>

            <rect x="245" y="14" width="190" height="58" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="340" y="36" textAnchor="middle">ReAct</text>
            <text x="340" y="52" textAnchor="middle" fontSize="9" opacity="0.65">tool order unknown → Q&amp;A</text>

            <rect x="480" y="14" width="190" height="58" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="575" y="36" textAnchor="middle">Plan-Execute</text>
            <text x="575" y="52" textAnchor="middle" fontSize="9" opacity="0.65">steps known → scheduled synthesis*</text>

            <rect x="10" y="152" width="190" height="46" rx="3" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.75" />
            <text x="105" y="171" textAnchor="middle" fontSize="10">Formatted list</text>
            <text x="105" y="184" textAnchor="middle" fontSize="8.5" opacity="0.65">no LLM synthesis</text>

            <rect x="245" y="152" width="425" height="46" rx="3" fill="none" stroke="var(--accent)" strokeWidth="1.8" />
            <text x="457" y="180" textAnchor="middle" fill="var(--accent)">synthesize_insight()</text>

            <path d="M105 72 L105 152" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />
            <path d="M340 72 L340 152" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />
            <path d="M575 72 L575 152" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />
          </g>
        </svg>
      </div>
      <figcaption>
        Router/dispatch peels off on its own — a plain lookup formatted into a list, no LLM synthesis. ReAct and
        Plan-Execute gather evidence differently but both feed the same shared reasoning core.
        *Plan-Execute exists in the codebase but isn&apos;t wired to the live scheduler yet — currently reachable
        only via a seed script, not the production ingestion path.
      </figcaption>
    </figure>
  );
}

export default function Technical() {
  return (
    <div className={`${styles.landing} ${styles.tpage}`}>
      <Head>
        <title>TickerThesis — Engineering Overview</title>
      </Head>

      <div className={styles.topbar}>
        <div className={styles.wrap}>
          <div className={styles.wordmark}>
            TICKER<span className={styles.dot}>·</span>THESIS
          </div>
          <Link href="/" className={styles.backLink}>
            ← Back to overview
          </Link>
        </div>
      </div>

      <section className={styles.techHero}>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>ENGINEERING OVERVIEW</div>
          <h1>TickerThesis — under the hood</h1>
          <p className={styles.subhead}>
            A personalized, evidence-cited news classification agent for ASX-listed companies — built to
            demonstrate production-oriented agentic AI design, not just a model wrapped in a chat box.
          </p>
          <p className={styles.pullquote}>
            Every claim is traceable to a source. Nothing is asserted beyond what the retrieved articles
            actually support.
          </p>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>PROBLEM FRAMING</div>
          <p className={styles.prose} style={{ marginTop: 16 }}>
            Searching for a company&apos;s news is a solved problem — anyone can Google it. The harder problem
            is organizing that unstructured firehose around what a specific person actually cares about,
            consistently, every day, without manual triage. This project builds an agent that classifies daily
            news against user-defined theses automatically, and answers follow-up questions using only retrieved
            evidence — every claim traceable to a source, nothing asserted beyond what the articles actually
            support.
          </p>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>ARCHITECTURE AT A GLANCE</div>

          <ArchitectureDiagram />
          <OrchestrationDiagram />

          <dl className={styles.stackList}>
            <div>
              <dt>Frontend</dt>
              <dd>Next.js, exported static and deployed to Azure Static Web Apps via its own GitHub Actions workflow on every push to main.</dd>
            </div>
            <div>
              <dt>Backend</dt>
              <dd>FastAPI, containerized and built via <code>az acr build</code>, deployed to Azure Container Apps via a separate GitHub Actions workflow on every push to main.</dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>
                <b>Supabase</b> (Postgres + pgvector + Auth), RLS-enforced. The frontend reads and writes
                Supabase directly for anything that needs no compute — listing feeds, tickers, and alerts. The
                two writes that do need compute (creating/editing a feed, asking a question) route through the
                backend instead.
              </dd>
            </div>
            <div>
              <dt>LLM</dt>
              <dd>
                Groq, two models used deliberately: <b>Llama 3.3 70B</b> for routing, classification summaries,
                and reasoning/synthesis, and a separate, stronger <b>gpt-oss-120B</b> used only as an LLM judge —
                for the advice-avoidance compliance check and eval scoring — so results aren&apos;t the same
                model grading its own homework.
              </dd>
            </div>
            <div>
              <dt>Orchestration</dt>
              <dd>
                LangGraph — three deliberately different patterns, chosen per task rather than defaulted. See
                diagrams above. (Plan-Execute is implemented but not yet wired to the live scheduler.)
              </dd>
            </div>
            <div>
              <dt>Memory</dt>
              <dd>Three distinct types — procedural, episodic, semantic — backed by a persistent Postgres-backed LangGraph store (survives process restarts, not just in-memory).</dd>
            </div>
            <div>
              <dt>Eval / observability</dt>
              <dd>
                A per-request step tracer (timing, tokens, result per guardrail/LLM/tool step) plus LangSmith&apos;s
                own cost/latency/error summary; an eval suite scoring groundedness, relevance, and
                advice-avoidance against both fixed fixtures and live sampled traffic; p50/p95/max latency and
                token percentiles; and a queryable alerts table for threshold trips — all surfaced on one admin
                dashboard.
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>ENGINEERING DECISIONS WORTH HIGHLIGHTING</div>
          <div className={styles.decisionList}>
            <div className={styles.decision}>
              <span className={styles.tag}>Guardrails</span>
              <p>
                <b>Explicit, separate checks — not just prompt instructions.</b> A recursion_limit and a
                per-request/per-user-daily token ceiling bound ReAct&apos;s cost and abort mid-run with a
                graceful decline rather than a partial answer; a per-feed similarity threshold stops an article
                being force-fit into an irrelevant thesis; every answer carries a disclaimer plus a deduped,
                reachability-checked reference list built from what was actually retrieved.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Security</span>
              <p>
                <b>RLS as the real security boundary.</b> The frontend never implements its own authorization
                logic — Postgres Row Level Security, tied to Supabase Auth&apos;s JWTs, is what actually stops
                one user from seeing another&apos;s data. Backend scripts that act outside a user session use
                the service-role key, which deliberately bypasses RLS — kept out of anything the frontend
                touches.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Cost</span>
              <p>
                <b>A cheap gate before every expensive one.</b> Daily news is matched against a thesis by
                pgvector similarity first; only articles that already clear that threshold get an LLM call at
                all — a one-sentence relevance summary, not a re-classification.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Architecture</span>
              <p>
                <b>Shared reasoning core.</b> ReAct and Plan-Execute converge on one{' '}
                <code>synthesize_insight()</code> function — they differ only in how evidence is gathered, not
                in how it&apos;s reasoned over. (Plan-Execute itself isn&apos;t wired to the scheduler yet — see
                the diagram above.)
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>CI/CD</span>
              <p>
                <b>Two real cloud deployments, not one.</b> Frontend and backend each build and deploy through
                their own GitHub Actions workflow on every push to main — a static export to Azure Static Web
                Apps, and a container build/push to ACR followed by an Azure Container Apps update.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>HOW THIS DIFFERS FROM SIMILAR TOOLS</div>
          <p className={styles.prose} style={{ marginTop: 16, color: 'var(--ink-soft)' }}>
            ThesisScore (thesisscore.com) uses similar language — &quot;investment thesis,&quot; AI alerts — but
            solves a different problem.
          </p>
          <div className={styles.compare}>
            <div className={styles.col}>
              <h4>ThesisScore</h4>
              <p>
                A portfolio-discipline / journaling tool. You write your own prediction, and it scores the
                quality of your reasoning, computes risk metrics (beta, VaR, drawdown), and sets exit criteria
                (target price, stop-loss).
              </p>
              <p>Core mechanism: evaluates <b style={{ color: 'var(--ink)' }}>user-generated text</b>.</p>
            </div>
            <div className={`${styles.col} ${styles.mine}`}>
              <h4>TickerThesis</h4>
              <p>
                Doesn&apos;t evaluate the user&apos;s own reasoning at all. &quot;Thesis&quot; here means a
                category the user defines to organize incoming news (Revenue Trend, Customer Churn); the system
                classifies external news articles into those categories and answers questions using only
                retrieved, cited evidence.
              </p>
              <p>Core mechanism: classifies and retrieves <b style={{ color: 'var(--ink)' }}>external evidence</b>.</p>
            </div>
          </div>
        </div>
      </section>

      <section style={{ borderBottom: 'none', paddingBottom: 100 }}>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>LINKS</div>
          <div className={styles.linksRow}>
            <span className={styles.linkChip}>Fig. 1 — Define a thesis<span className={styles.status}>image coming soon</span></span>
            <span className={styles.linkChip}>Fig. 2 — Daily evidence<span className={styles.status}>image coming soon</span></span>
            <span className={styles.linkChip}>Fig. 3 — Ask &amp; cite<span className={styles.status}>image coming soon</span></span>
            <span className={styles.linkChip}>GitHub repository<span className={styles.status}>link coming soon</span></span>
            <span className={styles.linkChip}>LinkedIn / contact<span className={styles.status}>link coming soon</span></span>
          </div>
        </div>
      </section>
    </div>
  );
}
