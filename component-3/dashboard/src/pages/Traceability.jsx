import { useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { Badge, Button, Callout, Card, ErrorPanel, Hash, JsonView, KeyValues, Loading, PageHeader, Stat, StatusBadge, Table, TechnicalDetails } from "../components/ui.jsx";
import { buildGraphCreateRequest } from "../lib/requests.js";
import { activeLinks, attentionLinks, buildRequirementChains, labelFor, linkNeedsAttention, nodeIndex, summarizeGraph } from "../lib/traceGraph.js";
import { formatTime } from "../lib/format.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

const MAX_VERSIONS_FETCHED = 12;

export function downloadText(filename, text, mimeType) {
  const anchor = document.createElement("a");
  anchor.download = filename;
  anchor.href = `data:${mimeType};charset=utf-8,${encodeURIComponent(text)}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function versionSummary(snapshot) {
  const summary = summarizeGraph(snapshot);
  return {
    graph_version: snapshot.graph_version,
    persisted_at_utc: snapshot.persisted_at_utc,
    generation_run_id: snapshot.generation_run_id,
    artifact_digest_sha256: snapshot.artifact_digest_sha256,
    graph_content_digest_sha256: snapshot.graph_content_digest_sha256,
    activeNodes: summary.activeNodeCount,
    activeLinks: summary.activeLinkCount,
    unresolved: summary.unresolvedLinkCount,
    reviewRequired: summary.reviewRequiredLinkCount,
  };
}

// Reads every stored version of a graph from the API (read-only).
export async function fetchVersionSummaries(graphId, latest) {
  const first = Math.max(1, latest - MAX_VERSIONS_FETCHED + 1);
  const rows = [];
  for (let version = first; version <= latest; version += 1) {
    const snapshot = await api.graphVersion(graphId, version);
    rows.push(versionSummary(snapshot));
  }
  return rows;
}

function Cell({ items, onSelect }) {
  if (items.length === 0) return <span className="muted small">none</span>;
  return (
    <div className="chip-row">
      {items.map(({ node, link }) => (
        <button
          key={node.node_id}
          type="button"
          className={`chip chip-button${linkNeedsAttention(link) ? " chip-warn" : " chip-ok"}`}
          title={`${link.relation_type} · ${link.resolution_status} · ${link.review_status}`}
          onClick={() => onSelect({ node, link })}
        >
          {linkNeedsAttention(link) ? "⚠ " : "✓ "}
          {node.label}
        </button>
      ))}
    </div>
  );
}

function Evidence({ selected, nodes }) {
  if (!selected) return <p className="muted small">Select a node chip or a link row to see its evidence.</p>;
  const { link } = selected;
  return (
    <div data-testid="link-evidence">
      <KeyValues
        items={[
          { label: "Link", value: <code>{link.link_id}</code> },
          { label: "Direction", value: `${labelFor(nodes, link.source_node_id)} —${link.relation_type}→ ${labelFor(nodes, link.target_node_id)}` },
          { label: "Resolution", value: <StatusBadge status={link.resolution_status} /> },
          { label: "Review", value: <StatusBadge status={link.review_status} /> },
          { label: "Lifecycle", value: link.lifecycle_status },
          { label: "Evidence kind", value: link.provenance.evidence_kind },
          { label: "Mapping rule", value: <code>{link.provenance.mapping_rule_id}</code> },
          { label: "Evidence refs", value: link.provenance.evidence_refs.join(", ") || "none" },
          { label: "Details", value: link.provenance.details },
        ]}
      />
    </div>
  );
}

export default function Traceability({ navigate }) {
  const { session, set } = useSession();
  const stored = session.generationRun;
  const graphState = session.graph;
  const snapshot = graphState?.snapshot;
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("ATTENTION");
  const [relation, setRelation] = useState("ALL");

  const build = useAction(async () => {
    const created = await api.createGraph(buildGraphCreateRequest(stored.run));
    const versions = await fetchVersionSummaries(created.graph_id, created.graph_version);
    set("graph", { snapshot: created, versions, fetchedAt: new Date().toISOString() });
    setSelected(null);
  });

  const refresh = useAction(async () => {
    const latest = await api.latestGraph(snapshot.graph_id);
    const versions = await fetchVersionSummaries(latest.graph_id, latest.graph_version);
    set("graph", { snapshot: latest, versions, fetchedAt: new Date().toISOString() });
  });

  const evidence = useAction(async () => {
    const [rtm, metrics] = await Promise.all([
      api.graphRtm(snapshot.graph_id, snapshot.graph_version),
      api.graphMetrics(snapshot.graph_id, snapshot.graph_version),
    ]);
    set("graph", { ...graphState, rtm, metrics, evidenceFetchedAt: new Date().toISOString() });
  });

  const summary = useMemo(() => (snapshot ? summarizeGraph(snapshot) : null), [snapshot]);
  const nodes = useMemo(() => (snapshot ? nodeIndex(snapshot) : new Map()), [snapshot]);
  const chains = useMemo(() => (snapshot ? buildRequirementChains(snapshot) : []), [snapshot]);
  const attention = useMemo(() => (snapshot ? attentionLinks(snapshot) : []), [snapshot]);
  const relations = useMemo(() => (snapshot ? Object.keys(summary.linkCountsByRelation).sort() : []), [snapshot, summary]);
  const shownLinks = useMemo(() => {
    if (!snapshot) return [];
    let rows = filter === "ATTENTION" ? attention : activeLinks(snapshot);
    if (relation !== "ALL") rows = rows.filter((link) => link.relation_type === relation);
    return rows;
  }, [snapshot, filter, relation, attention]);

  return (
    <div className="page">
      <PageHeader
        title="Living Traceability"
        subtitle="A persistent, versioned evidence graph from requirement → UML → code → API → database → test hook."
        badges={<Badge tone="info">REAL C3 API</Badge>}
      />

      {!stored ? (
        <Callout tone="warn" title="Generation run required">
          The graph is built from a verified generation manifest.{" "}
          <button type="button" className="link-button" onClick={() => navigate("generation")}>Go to Code Generation</button>
        </Callout>
      ) : null}

      <Card
        title="Build a verified graph snapshot"
        subtitle="The backend verifies manifest, workspace hashes, artifact digest, and run evidence before accepting the graph."
        actions={<Button onClick={() => build.run()} loading={build.loading} disabled={!stored}>{snapshot ? "Rebuild graph (adds a version)" : "Build traceability graph"}</Button>}
      >
        {stored ? <p className="small">Source run <code>{stored.run.manifest.generation_run_id}</code> · {stored.mode}</p> : null}
        {build.loading ? <Loading label="Building and persisting graph" startedAt={build.startedAt} /> : null}
        <ErrorPanel error={build.error} context="Graph build" />
      </Card>

      {snapshot ? (
        <>
          <div className="stats">
            <Stat label="Graph version" value={`v${snapshot.graph_version}`} hint={`graph ${snapshot.graph_id.slice(0, 8)}…`} />
            <Stat label="Active nodes" value={summary.activeNodeCount} />
            <Stat label="Active links" value={summary.activeLinkCount} />
            <Stat label="Resolved links" value={summary.resolvedLinkCount} tone="ok" />
            <Stat label="Unresolved links" value={summary.unresolvedLinkCount} tone={summary.unresolvedLinkCount ? "warn" : undefined} />
            <Stat label="Review required" value={summary.reviewRequiredLinkCount} tone={summary.reviewRequiredLinkCount ? "warn" : undefined} />
          </div>

          <div className="grid grid-2">
            <Card
              title="Graph content"
              actions={<Button variant="secondary" onClick={() => refresh.run()} loading={refresh.loading}>Refresh from API</Button>}
            >
              <KeyValues
                items={[
                  { label: "Content digest", value: <Hash value={snapshot.graph_content_digest_sha256} length={24} /> },
                  { label: "Artifact digest", value: <Hash value={snapshot.artifact_digest_sha256} length={24} /> },
                  { label: "Persisted", value: formatTime(snapshot.persisted_at_utc) },
                  { label: "Direction policy", value: snapshot.relation_direction_policy_version },
                  { label: "Retired nodes / links", value: `${summary.retiredNodeCount} / ${summary.retiredLinkCount}` },
                ]}
              />
              <ErrorPanel error={refresh.error} context="Refresh" />
              <h3 className="subhead">Nodes by type</h3>
              <div className="chip-row">
                {Object.entries(summary.nodeCountsByType).map(([type, count]) => (<span key={type} className="chip">{type} · {count}</span>))}
              </div>
              <h3 className="subhead">Links by relation</h3>
              <div className="chip-row">
                {Object.entries(summary.linkCountsByRelation).map(([type, count]) => (<span key={type} className="chip">{type} · {count}</span>))}
              </div>
            </Card>
            <Card title="Coverage" subtitle={`${snapshot.coverage.policy_version}: ${snapshot.coverage.verified_count} verified · ${snapshot.coverage.partial_count} partial · ${snapshot.coverage.unresolved_count} unresolved`}>
              <Table
                dense
                rowKey={(row) => row.requirement_id}
                rows={snapshot.coverage.requirements}
                columns={[
                  { key: "requirement_id", header: "Requirement" },
                  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
                  { key: "impl", header: "Implemented by", render: (row) => row.implementing_node_ids.length },
                  { key: "ver", header: "Verified by", render: (row) => row.verifying_node_ids.length },
                  { key: "unr", header: "Unresolved", render: (row) => row.unresolved_link_ids.length },
                ]}
              />
              {snapshot.coverage.diagnostics.missing_evidence.length ? (
                <Callout tone="warn" title="Missing evidence">{snapshot.coverage.diagnostics.missing_evidence.join("; ")}</Callout>
              ) : null}
            </Card>
          </div>

          <Card
            title="RTM export and trace diagnostics"
            subtitle="Read-only reports from the persisted graph version; diagnostics report gaps without blocking existing flows."
            actions={(
              <Button variant="secondary" onClick={() => evidence.run()} loading={evidence.loading}>
                Load RTM and diagnostics
              </Button>
            )}
          >
            <ErrorPanel error={evidence.error} context="RTM and trace diagnostics" />
            {graphState.rtm && graphState.metrics ? (
              <>
                <div className="stats">
                  <Stat label="RTM requirements" value={graphState.rtm.rows.length} />
                  <Stat label="Requirement coverage" value={`${(graphState.metrics.coverage_rate * 100).toFixed(1)}%`} tone={graphState.metrics.coverage_gaps.length ? "warn" : "ok"} />
                  <Stat label="Orphan nodes" value={graphState.metrics.orphan_node_count} tone={graphState.metrics.orphan_node_count ? "warn" : "ok"} />
                </div>
                <div className="button-row">
                  <Button
                    variant="secondary"
                    onClick={() => downloadText(
                      `rtm-${snapshot.graph_id}-v${snapshot.graph_version}.json`,
                      `${JSON.stringify(graphState.rtm, null, 2)}\n`,
                      "application/json",
                    )}
                  >
                    Export RTM JSON
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => downloadText(
                      `rtm-${snapshot.graph_id}-v${snapshot.graph_version}.md`,
                      `${graphState.rtm.table_markdown}\n`,
                      "text/markdown",
                    )}
                  >
                    Export RTM table
                  </Button>
                </div>
                {graphState.metrics.diagnostics.length ? graphState.metrics.diagnostics.map((diagnostic) => (
                  <Callout key={diagnostic.code} tone="warn" title={diagnostic.code}>
                    {diagnostic.message} Affected identities: {diagnostic.affected_ids.join(", ")}.
                  </Callout>
                )) : (
                  <Callout tone="ok" title="No orphan or coverage-gap diagnostics">
                    This deterministic report found no active orphan downstream nodes or uncovered requirements in graph v{snapshot.graph_version}.
                  </Callout>
                )}
              </>
            ) : <p className="muted small">Load the reports to inspect and export the RTM for this exact graph version.</p>}
          </Card>

          <Card title="Requirement traceability chains" subtitle="✓ resolved link · ⚠ unresolved or review required. Click a chip for its evidence.">
            <Table
              rowKey={(row) => row.requirement.node_id}
              rows={chains}
              columns={[
                { key: "req", header: "Requirement", render: (row) => (<><strong>{row.requirement.source_identity}</strong><div className="muted small">{row.requirement.label}</div></>) },
                { key: "design", header: "UML / design", render: (row) => <Cell items={row.design} onSelect={setSelected} /> },
                { key: "code", header: "Code", render: (row) => <Cell items={row.code} onSelect={setSelected} /> },
                { key: "api", header: "API", render: (row) => <Cell items={row.api} onSelect={setSelected} /> },
                { key: "db", header: "Database", render: (row) => <Cell items={row.database} onSelect={setSelected} /> },
                { key: "tests", header: "Test hooks", render: (row) => <Cell items={row.tests} onSelect={setSelected} /> },
              ]}
            />
          </Card>

          <div className="grid grid-2">
            <Card
              title="Links"
              actions={
                <div className="filter-row">
                  <select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Link filter">
                    <option value="ATTENTION">Needs attention ({attention.length})</option>
                    <option value="ALL">All active links ({summary.activeLinkCount})</option>
                  </select>
                  <select value={relation} onChange={(event) => setRelation(event.target.value)} aria-label="Relation filter">
                    <option value="ALL">All relations</option>
                    {relations.map((item) => (<option key={item} value={item}>{item}</option>))}
                  </select>
                </div>
              }
            >
              <Table
                dense
                empty={filter === "ATTENTION" ? "No unresolved or review-required links in the active graph." : "No links match."}
                rowKey={(row) => row.link_id}
                selectedKey={selected?.link.link_id}
                onRowClick={(link) => setSelected({ link })}
                rows={shownLinks}
                columns={[
                  { key: "src", header: "Source", render: (row) => labelFor(nodes, row.source_node_id) },
                  { key: "rel", header: "Relation", render: (row) => <code>{row.relation_type}</code> },
                  { key: "tgt", header: "Target", render: (row) => labelFor(nodes, row.target_node_id) },
                  { key: "res", header: "Resolution", render: (row) => <StatusBadge status={row.resolution_status} /> },
                  { key: "rev", header: "Review", render: (row) => <StatusBadge status={row.review_status} /> },
                ]}
              />
            </Card>
            <Card title="Evidence">
              <Evidence selected={selected} nodes={nodes} />
            </Card>
          </div>

          <Card title="Graph versions" subtitle="Read from GET /traceability/graphs/{id}/versions/{n}. Versions are immutable.">
            <Table
              dense
              rowKey={(row) => row.graph_version}
              rows={graphState.versions}
              columns={[
                { key: "graph_version", header: "Version", render: (row) => `v${row.graph_version}` },
                { key: "run", header: "Generation run", render: (row) => <Hash value={row.generation_run_id} length={8} /> },
                { key: "art", header: "Artifact digest", render: (row) => <Hash value={row.artifact_digest_sha256} /> },
                { key: "dig", header: "Graph digest", render: (row) => <Hash value={row.graph_content_digest_sha256} /> },
                { key: "n", header: "Nodes", render: (row) => row.activeNodes },
                { key: "l", header: "Links", render: (row) => row.activeLinks },
                { key: "u", header: "Unresolved", render: (row) => row.unresolved },
                { key: "t", header: "Persisted", render: (row) => formatTime(row.persisted_at_utc) },
              ]}
            />
            {snapshot.graph_version > MAX_VERSIONS_FETCHED ? <p className="muted small">Showing the latest {MAX_VERSIONS_FETCHED} versions only.</p> : null}
          </Card>
          <div className="button-row">
            <Button onClick={() => navigate("scoped")}>Continue to Scoped Regeneration</Button>
          </div>
          <TechnicalDetails summary="Graph snapshot and machine-readable evidence">
            <JsonView value={snapshot} summary="Open full graph JSON" />
          </TechnicalDetails>
        </>
      ) : null}
    </div>
  );
}
