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

function AskFlowDetail() {
  return (
    <details className={styles.expandBox}>
      <summary>See the full step-by-step for a chat question</summary>
      <div className={styles.expandBody}>
        <div className={styles.legendRow}>
          <span><i className={`${styles.legendSwatch} ${styles.py}`} />Python &middot; deterministic code</span>
          <span><i className={`${styles.legendSwatch} ${styles.llm}`} />Claude call &middot; LLM</span>
          <span><i className={`${styles.legendSwatch} ${styles.exit}`} />Terminal / short-circuit exit</span>
        </div>

        <figure className={styles.diagramFigure}>
          <div className={styles.diagramScroll}>
            <svg
              viewBox="0 0 780 840"
              role="img"
              aria-label="After the frontend posts a question, entry guardrails check auth, rate limit and daily token budget in plain Python. The router then runs a regex advice-seeking scan in Python, a classify_request LLM call that returns category, ticker and an is_advice_seeking flag, a Python ticker-validation gate, and a Python check of the LLM's advice-seeking flag - any of the three gates can short-circuit straight to a declined response, shown as one shared exit box. A clean request branches by category. search_news is pure Python: yfinance headlines, no LLM, no synthesis, and it skips straight to the final response step. conduct_analysis first builds a prompt in Python by fetching procedural instructions and episodic examples, then runs a ReAct loop that alternates an LLM reasoning turn with Python tool execution and a per-call token-budget check, repeating until the LLM produces a final answer. That evidence goes through synthesize_insight, an LLM call, then an output guardrail: a Python regex scan followed, if clean, by an LLM judge call, either of which can still decline the answer. A passing insight is stored as a new episodic memory entry in Python. Both the search_news path and the conduct_analysis success path converge on one final Python step that filters unreachable reference links, logs the request trace, and returns the answer JSON, which the frontend then renders."
            >
              <defs>
                <marker id="arrow3" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
                </marker>
                <marker id="arrow3llm" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)" />
                </marker>
                <marker id="arrow3exit" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="currentColor" opacity="0.6" />
                </marker>
              </defs>

              <g fontFamily="var(--mono)" fill="currentColor">
                {/* Entry guardrails */}
                <rect x="210" y="14" width="360" height="52" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="390" y="36" textAnchor="middle" fontSize="11.5">Entry guardrails</text>
                <text x="390" y="51" textAnchor="middle" fontSize="9" opacity="0.65">verify Supabase JWT &middot; rate limit &middot; daily token ceiling</text>

                <path d="M390,66 L102,90" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />

                {/* Router row */}
                <rect x="14" y="90" width="176" height="58" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="102" y="112" textAnchor="middle" fontSize="11.5">Regex scan</text>
                <text x="102" y="127" textAnchor="middle" fontSize="9" opacity="0.65">obvious advice-seeking</text>
                <text x="102" y="139" textAnchor="middle" fontSize="9" opacity="0.65">phrasing, no LLM</text>

                <rect x="210" y="90" width="176" height="58" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
                <text x="298" y="112" textAnchor="middle" fontSize="11.5" fill="var(--accent)">classify_request()</text>
                <text x="298" y="127" textAnchor="middle" fontSize="9" fill="var(--accent)" opacity="0.8">Haiku &middot; category, ticker,</text>
                <text x="298" y="139" textAnchor="middle" fontSize="9" fill="var(--accent)" opacity="0.8">is_advice_seeking</text>

                <rect x="406" y="90" width="176" height="58" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="494" y="112" textAnchor="middle" fontSize="11.5">Validate ticker</text>
                <text x="494" y="127" textAnchor="middle" fontSize="9" opacity="0.65">real, resolvable</text>
                <text x="494" y="139" textAnchor="middle" fontSize="9" opacity="0.65">ASX symbol</text>

                <rect x="602" y="90" width="164" height="58" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="684" y="112" textAnchor="middle" fontSize="11.5">Advice gate</text>
                <text x="684" y="127" textAnchor="middle" fontSize="9" opacity="0.65">checks the LLM&apos;s own</text>
                <text x="684" y="139" textAnchor="middle" fontSize="9" opacity="0.65">is_advice_seeking flag</text>

                <path d="M190,119 L210,119" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />
                <path d="M386,119 L406,119" stroke="var(--accent)" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3llm)" />
                <path d="M582,119 L602,119" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />

                {/* declined (input) */}
                <rect x="280" y="170" width="220" height="50" rx="4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.75" />
                <text x="390" y="190" textAnchor="middle" fontSize="11.5">Declined</text>
                <text x="390" y="204" textAnchor="middle" fontSize="8.5" opacity="0.65">TICKER_NOT_FOUND / ADVICE_SEEKING</text>

                <path d="M102,148 Q102,160 330,170" stroke="currentColor" strokeWidth="1.1" strokeDasharray="3 3" fill="none" opacity="0.6" markerEnd="url(#arrow3exit)" />
                <text x="150" y="163" textAnchor="middle" fontSize="8.5" opacity="0.6">matched</text>
                <path d="M494,148 L420,170" stroke="currentColor" strokeWidth="1.1" strokeDasharray="3 3" fill="none" opacity="0.6" markerEnd="url(#arrow3exit)" />
                <text x="478" y="162" textAnchor="middle" fontSize="8.5" opacity="0.6">fails</text>
                <path d="M684,148 Q684,160 470,170" stroke="currentColor" strokeWidth="1.1" strokeDasharray="3 3" fill="none" opacity="0.6" markerEnd="url(#arrow3exit)" />
                <text x="630" y="163" textAnchor="middle" fontSize="8.5" opacity="0.6">flag = true</text>

                {/* pass path + branch */}
                <path d="M684,148 L684,232 L536,232 L536,254" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />
                <path d="M684,232 L146,232 L146,256" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />
                <text x="270" y="226" textAnchor="middle" fontSize="8.5" opacity="0.6">category = search_news</text>
                <text x="610" y="226" textAnchor="middle" fontSize="8.5" opacity="0.6">category = conduct_analysis</text>

                {/* search_news terminal */}
                <rect x="30" y="256" width="232" height="70" rx="4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.85" />
                <text x="146" y="278" textAnchor="middle" fontSize="11.5">search_news()</text>
                <text x="146" y="293" textAnchor="middle" fontSize="9" opacity="0.65">yfinance headlines &mdash; no LLM,</text>
                <text x="146" y="305" textAnchor="middle" fontSize="9" opacity="0.65">no synthesis</text>
                <text x="146" y="318" textAnchor="middle" fontSize="8" opacity="0.5" fontStyle="italic">&quot;news on TLS.AX?&quot;</text>

                {/* conduct_analysis lane */}
                <rect x="322" y="240" width="428" height="410" rx="6" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 3" opacity="0.4" />
                <text x="536" y="258" textAnchor="middle" fontSize="10" letterSpacing="0.04em" opacity="0.7">
                  conduct_analysis_node() &middot; open / &quot;why&quot; questions
                </text>

                <rect x="356" y="270" width="360" height="50" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="536" y="290" textAnchor="middle" fontSize="11.5">Build prompt</text>
                <text x="536" y="305" textAnchor="middle" fontSize="9" opacity="0.65">fetch procedural instructions + episodic examples (vector search)</text>

                <path d="M536,320 L536,346" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />

                {/* react loop */}
                <rect x="356" y="346" width="168" height="60" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
                <text x="440" y="368" textAnchor="middle" fontSize="11.5" fill="var(--accent)">LLM reasons</text>
                <text x="440" y="383" textAnchor="middle" fontSize="9" fill="var(--accent)" opacity="0.8">Sonnet &middot; picks a tool,</text>
                <text x="440" y="396" textAnchor="middle" fontSize="9" fill="var(--accent)" opacity="0.8">or gives final answer</text>

                <rect x="548" y="346" width="168" height="60" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="632" y="368" textAnchor="middle" fontSize="11.5">Run tool + check_token()</text>
                <text x="632" y="383" textAnchor="middle" fontSize="9" opacity="0.65">news / price / report search,</text>
                <text x="632" y="396" textAnchor="middle" fontSize="9" opacity="0.65">then per-call token ceiling</text>

                <path d="M524,362 L548,362" stroke="currentColor" strokeWidth="1.1" fill="none" markerEnd="url(#arrow3)" />
                <text x="536" y="356" textAnchor="middle" fontSize="8.5" opacity="0.6">tool call</text>
                <path d="M548,390 L524,390" stroke="currentColor" strokeWidth="1.1" fill="none" markerEnd="url(#arrow3)" />
                <text x="536" y="411" textAnchor="middle" fontSize="8.5" opacity="0.6">next turn, until final answer</text>

                <path d="M440,406 L440,430 L536,430 L536,450" stroke="var(--accent)" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3llm)" />
                <text x="474" y="424" textAnchor="middle" fontSize="8.5" fill="var(--accent)" opacity="0.85">final answer</text>

                <rect x="416" y="456" width="240" height="56" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.8" />
                <text x="536" y="480" textAnchor="middle" fontSize="12" fill="var(--accent)">synthesize_insight()</text>
                <text x="536" y="497" textAnchor="middle" fontSize="9" fill="var(--accent)" opacity="0.8">Sonnet &middot; connects all gathered evidence</text>

                <path d="M536,512 L536,528" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />

                <rect x="356" y="534" width="168" height="50" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="440" y="554" textAnchor="middle" fontSize="11.5">Regex scan</text>
                <text x="440" y="569" textAnchor="middle" fontSize="9" opacity="0.65">advice-language keywords</text>

                <rect x="548" y="534" width="168" height="50" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
                <text x="632" y="552" textAnchor="middle" fontSize="11.5" fill="var(--accent)">LLM judge</text>
                <text x="632" y="567" textAnchor="middle" fontSize="9" fill="var(--accent)" opacity="0.8">Opus &middot; check_advice_avoidance()</text>

                <path d="M524,559 L548,559" stroke="currentColor" strokeWidth="1.1" fill="none" markerEnd="url(#arrow3)" />
                <text x="536" y="551" textAnchor="middle" fontSize="8.5" opacity="0.6">clean</text>

                {/* output guardrail exits */}
                <rect x="602" y="600" width="164" height="46" rx="4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.75" />
                <text x="684" y="619" textAnchor="middle" fontSize="11.5">Declined</text>
                <text x="684" y="633" textAnchor="middle" fontSize="8.5" opacity="0.65">ADVICE_LANGUAGE_DETECTED</text>

                <rect x="372" y="600" width="200" height="46" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="472" y="619" textAnchor="middle" fontSize="11.5">Store episodic memory</text>
                <text x="472" y="633" textAnchor="middle" fontSize="8.5" opacity="0.65">so a similar future question retrieves it</text>

                <path d="M440,584 Q470,594 620,600" stroke="currentColor" strokeWidth="1.1" strokeDasharray="3 3" fill="none" opacity="0.6" markerEnd="url(#arrow3exit)" />
                <text x="500" y="592" textAnchor="middle" fontSize="8.5" opacity="0.6">matched</text>
                <path d="M600,584 L500,600" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />
                <text x="590" y="592" textAnchor="middle" fontSize="8.5" opacity="0.6">passed</text>
                <path d="M664,584 L684,600" stroke="currentColor" strokeWidth="1.1" strokeDasharray="3 3" fill="none" opacity="0.6" markerEnd="url(#arrow3exit)" />
                <text x="690" y="592" textAnchor="middle" fontSize="8.5" opacity="0.6">flagged</text>

                {/* merge into final response step */}
                <path d="M146,326 L146,680 L260,690" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />
                <path d="M472,646 L410,690" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />

                <rect x="230" y="694" width="320" height="60" rx="4" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <text x="390" y="717" textAnchor="middle" fontSize="11.5">Filter references &middot; log trace</text>
                <text x="390" y="732" textAnchor="middle" fontSize="9" opacity="0.65">drops unreachable links, returns</text>
                <text x="390" y="744" textAnchor="middle" fontSize="9" opacity="0.65">{'{answer, ticker, category, references}'}</text>

                <path d="M390,754 L390,776" stroke="currentColor" strokeWidth="1.2" fill="none" markerEnd="url(#arrow3)" />

                <rect x="255" y="782" width="270" height="34" rx="4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.75" />
                <text x="390" y="804" textAnchor="middle" fontSize="11.5">Frontend re-renders AnswerBlock</text>
              </g>
            </svg>
          </div>
          <figcaption>
            Two-layer guardrails bookend the pipeline &mdash; a cheap regex gate before every expensive LLM call, both
            on the way in (advice-seeking phrasing, ticker validity) and on the way out (advice-language detection,
            checked by an Opus judge only once the regex layer passes clean). <code>search_news</code> never touches{' '}
            <code>synthesize_insight()</code> or the output guardrail at all &mdash; it has no LLM-generated text to
            check, so it skips straight to the shared response step. Amber boxes are the only steps that spend an
            LLM call; every other box is deterministic Python against Postgres, yfinance, or the embedding index.
          </figcaption>
        </figure>
      </div>
    </details>
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
            questions — every claim traceable to a source, and every synthesis willing to say plainly
            when the evidence isn&apos;t enough to draw a conclusion, rather than forcing one.
          </p>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>ARCHITECTURE AT A GLANCE</div>

          <ArchitectureDiagram />
          <OrchestrationDiagram />
          <AskFlowDetail />

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
                Claude, three tiers used deliberately, cheapest to strongest: <b>Haiku 4.5</b> for routing and
                other high-volume, low-complexity calls; <b>Sonnet 5</b> for the actual reasoning work — ReAct,
                cross-evidence synthesis, insight planning; and a separate, stronger <b>Opus 5</b> used only as
                an LLM judge — for the advice-avoidance compliance check and eval scoring — so results
                aren&apos;t the same model grading its own homework.
              </dd>
            </div>
            <div>
              <dt>Orchestration</dt>
              <dd>
                LangGraph — three deliberately different patterns, chosen per task rather than defaulted. See
                diagrams above. Plan-Execute runs inside the ingestion pipeline, synthesizing each user&apos;s
                cross-feed insight right after their feeds are classified.
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
                in how it&apos;s reasoned over. ReAct runs live, per user question; Plan-Execute runs as the
                ingestion pipeline&apos;s own insight-synthesis phase — see the diagram above.
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
