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
          aria-label="Frontend talks directly to Supabase for reads and for writes that need no server-side compute, under Row Level Security. The backend is only in the loop for writes that need compute: generating a feed's embedding, or running the ask-a-question agent. It reads evidence back from Supabase and calls Claude to classify and reason, writing results back to Supabase."
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
            <text x="585" y="174" textAnchor="middle">Claude</text>
            <text x="585" y="190" textAnchor="middle" fontSize="9" opacity="0.65">Haiku · Sonnet · Opus</text>

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
          viewBox="0 0 700 300"
          role="img"
          aria-label="Two separate triggers, not one decision point. A user's chat question hits Router/dispatch: a known-shape lookup like 'news on TLS.AX' returns a formatted list with no LLM involved, an open question like 'why is profit rising' goes to ReAct instead. Separately, with no user waiting, an ingestion pipeline run triggers Plan-Execute, which plans which feeds to review then works through each one. ReAct and Plan-Execute gather evidence completely differently, but both hand off to the same shared synthesize_insight function - Router/dispatch's list path never does."
        >
          <defs>
            <marker id="arrow2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
            </marker>
          </defs>

          <g fontFamily="var(--mono)" fill="currentColor">
            {/* lane headers */}
            <text x="175" y="18" textAnchor="middle" fontSize="10" letterSpacing="0.04em" opacity="0.7">
              TRIGGER · user asks a question
            </text>
            <text x="525" y="18" textAnchor="middle" fontSize="10" letterSpacing="0.04em" opacity="0.7">
              TRIGGER · ingestion pipeline run
            </text>

            {/* lanes */}
            <rect x="10" y="28" width="330" height="180" rx="4" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 3" opacity="0.4" />
            <rect x="360" y="28" width="330" height="180" rx="4" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 3" opacity="0.4" />

            {/* left lane: router splits into two */}
            <rect x="60" y="42" width="230" height="46" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="175" y="61" textAnchor="middle" fontSize="11">Router / dispatch</text>
            <text x="175" y="76" textAnchor="middle" fontSize="9" opacity="0.65">classifies the question&apos;s shape</text>

            <rect x="30" y="140" width="130" height="58" rx="3" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.8" />
            <text x="95" y="161" textAnchor="middle" fontSize="10.5">Formatted list</text>
            <text x="95" y="175" textAnchor="middle" fontSize="8.5" opacity="0.65">no LLM synthesis</text>
            <text x="95" y="188" textAnchor="middle" fontSize="8" opacity="0.5">&quot;news on TLS.AX?&quot;</text>

            <rect x="180" y="140" width="130" height="58" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="245" y="161" textAnchor="middle" fontSize="10.5">ReAct</text>
            <text x="245" y="175" textAnchor="middle" fontSize="8.5" opacity="0.65">evidence, tool by tool</text>
            <text x="245" y="188" textAnchor="middle" fontSize="8" opacity="0.5">&quot;why is profit rising?&quot;</text>

            <path d="M175,88 L100,140" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />
            <text x="120" y="112" textAnchor="middle" fontSize="8" opacity="0.6">known shape</text>
            <path d="M175,88 L245,140" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />
            <text x="228" y="112" textAnchor="middle" fontSize="8" opacity="0.6">open question</text>

            {/* right lane: plan then execute */}
            <rect x="410" y="42" width="230" height="46" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="525" y="61" textAnchor="middle" fontSize="11">Plan</text>
            <text x="525" y="76" textAnchor="middle" fontSize="9" opacity="0.65">picks which feeds, and in what order</text>

            <path d="M525,88 L525,140" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />

            <rect x="410" y="140" width="230" height="58" rx="3" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <text x="525" y="161" textAnchor="middle" fontSize="10.5">Execute steps</text>
            <text x="525" y="175" textAnchor="middle" fontSize="8.5" opacity="0.65">pulls each feed&apos;s items in turn</text>
            <text x="525" y="188" textAnchor="middle" fontSize="8" opacity="0.5">repeats once per feed</text>

            {/* convergence */}
            <path d="M245,198 L270,232" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />
            <path d="M525,198 L430,232" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow2)" />

            <rect x="170" y="232" width="360" height="50" rx="3" fill="none" stroke="var(--accent)" strokeWidth="1.8" />
            <text x="350" y="262" textAnchor="middle" fill="var(--accent)" fontSize="12">synthesize_insight()</text>
          </g>
        </svg>
      </div>
      <figcaption>
        Two separate triggers, not one decision point. A chat question hits Router/dispatch first — a known-shape
        lookup gets a formatted list with no LLM involved, anything open-ended goes to ReAct. An ingestion pipeline
        run triggers Plan-Execute instead, with no user waiting on it. ReAct and Plan-Execute gather evidence
        completely differently, but both hand off to the same shared <code>synthesize_insight()</code> reasoning
        core — Router/dispatch&apos;s list path never does.
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
            Grounded in retrieved evidence, not general knowledge — and honest, by design, when that
            evidence runs thin.
          </p>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>PROBLEM FRAMING</div>
          <p style={{ marginTop: 16 }}>
            Searching for a company&apos;s news is a solved problem — anyone can Google it. The harder
            problems sit underneath that:
          </p>

          <div className={styles.decisionList} style={{ marginTop: 20 }}>
            <div className={styles.decision}>
              <span className={styles.tag}>Organize</span>
              <p>
                Organizing that unstructured firehose around what a specific person actually cares about,
                consistently, every day, without manual triage.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Synthesize</span>
              <p>
                Turning a pile of individually-classified articles into an actual picture of what&apos;s
                going on, without overstating what the evidence supports.
              </p>
            </div>
          </div>

          <p style={{ marginTop: 24 }}>
            This project builds an agent that classifies daily news against user-defined theses,
            synthesizes a connected insight across each ticker&apos;s theses, and answers follow-up
            questions — every synthesis willing to say plainly when the evidence isn&apos;t enough to draw
            a conclusion, rather than forcing one.
          </p>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>ARCHITECTURE — 3 COMPONENTS</div>
          <p style={{ marginTop: 16 }}>
            Feed-News Matching (an ML classifier), Ask Question (a reactive RAG agent), and Summary
            Generation (a proactive digest pipeline) — three different problems, three deliberately
            different patterns, sharing one reasoning core.
          </p>

          <ArchitectureDiagram />
          <OrchestrationDiagram />
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>HOW EACH COMPONENT REASONS</div>
          <div className={styles.decisionList}>
            <div className={styles.decision}>
              <span className={styles.tag}>Memory</span>
              <p>
                Three long-term types — procedural (how to reason), episodic (past Q&amp;A precedent),
                semantic (durable company facts) — plus a short-term thread checkpoint for the current
                conversation. All three help the <i>agent</i> reason better; none of them change based on
                who&apos;s asking today. The one channel actually built for real per-user
                personalization — procedural memory&apos;s write path — has no live caller yet, so every
                user gets the same default reasoning rule.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>ReAct</span>
              <p>
                Chat Answer&apos;s <code>conduct_analysis</code> runs a ReAct agent against 7 tools — 5
                research tools plus 2 semantic-memory tools — with a mandatory source order baked into the prompt: cached
                internal news first, reports or fresh external news next, peers only for an explicit
                comparison. The loop stops the moment the model makes a turn with no tool call — treated
                as a research handoff, not a final answer. A separate <code>synthesize_insight()</code>{' '}
                call re-grounds the actual response directly against the gathered evidence.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Plan-Execute</span>
              <p>
                Summary Generation&apos;s proactive per-ticker digest has no user question to react to, so
                it runs a fixed plan
                instead: decide which feeds need extra evidence (reports, peer news), summarize each feed
                in turn, then synthesize one cross-feed insight. The harder design call: a feed always gets
                a real, explained summary even when its evidence is judged insufficient — the gap is
                stated plainly, not silently dropped.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>PRODUCTION RELIABILITY</div>
          <div className={styles.decisionList}>
            <div className={styles.decision}>
              <span className={styles.tag}>Guardrails</span>
              <p>
                Two layers — a cheap regex scan, then an LLM judge — on both the input (is this asking for
                advice?) and the output (does this answer give advice?) sides, fail-fast so the expensive
                check only runs once the cheap one is clean. The output judge deliberately runs on a
                stronger model than the one that wrote the answer, so it&apos;s never grading its own
                homework. Not yet covered: jailbreak and prompt-injection defenses — a known next step,
                distinct from this advice-avoidance check.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Evaluation</span>
              <p>
                Two parallel paths, both scored by an independent judge model that never generated the
                content being judged: offline, fixed-fixture evals catch regressions from a prompt or
                model change; continuous, rate-capped sampling of real production traffic catches live
                drift. Groundedness and completeness are covered everywhere; relevance is currently scored
                on live traffic only, not yet added to the fixed fixtures — a known coverage gap, not an
                oversight.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Observability</span>
              <p>
                A per-request step tracer records timing, tokens, and outcome for every guardrail, LLM,
                and tool call, alongside LangSmith&apos;s own cost/latency/error view. p50/p95/max latency
                and token percentiles, plus a queryable alerts table for threshold trips, all surface on
                one admin dashboard — not scattered across separate tools.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>DATA, MODELS &amp; COST</div>
          <div className={styles.decisionList}>
            <div className={styles.decision}>
              <span className={styles.tag}>Data &amp; API</span>
              <p>
                Postgres + pgvector is the only datastore — structured rows and embeddings live together,
                no separate vector database to keep in sync. Row Level Security, tied to Supabase Auth, is
                the real authorization boundary; the frontend never implements its own. The backend is
                only in the request path for the two operations that need real compute — creating/editing
                a feed and asking a question — everything else reads and writes Supabase directly.
              </p>
            </div>
            <div className={styles.decision}>
              <span className={styles.tag}>Model Choice</span>
              <p>
                Three Claude tiers, used deliberately rather than one model everywhere: Haiku handles
                routing and other high-volume, low-complexity calls; Sonnet does the actual reasoning —
                ReAct, synthesis, insight planning; Opus is reserved for judging — evals, guardrail checks,
                monitoring — never the model that generated what it&apos;s grading. Feed classification
                skips the LLM entirely: a local embedding model plus a tuned similarity threshold, since
                running an LLM call on every incoming article doesn&apos;t scale.
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
                classifies external news articles into those categories, synthesizes what they add up to into
                one connected insight per ticker, and answers questions using only retrieved, cited evidence.
              </p>
              <p>
                Core mechanism: classifies, synthesizes, and retrieves{' '}
                <b style={{ color: 'var(--ink)' }}>external evidence</b>.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
