import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  History,
  Code2,
  PlayCircle,
  RefreshCw,
  Plus,
  Upload,
  Eye,
  Copy,
  Check,
  Search,
  FileCode,
  Tag,
  ArrowUpRight,
  Filter,
} from 'lucide-react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import EmptyState from '../components/common/EmptyState';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import CodeViewer from '../components/common/CodeViewer';
import Modal from '../components/common/Modal';
import Pagination from '../components/common/Pagination';
import { getSubmissions } from '../api/submissionApi';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';
import { SUBMISSION_SOURCES } from '../utils/constants';

export default function SubmissionHistoryPage() {
  const navigate = useNavigate();

  const [submissions, setSubmissions] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const limit = 10;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  // Search filter
  const [searchTerm, setSearchTerm] = useState('');

  // Selected submission modal
  const [activeSubmission, setActiveSubmission] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const fetchSubmissions = async (offset = skip, isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const data = await getSubmissions({ skip: offset, limit });
      setSubmissions(data.items || []);
      setTotal(data.total || 0);
      setSkip(offset);
    } catch (err) {
      setError(err.message || 'Failed to load submission history.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchSubmissions(0);
  }, []);

  const handleCopy = async (id) => {
    try {
      await navigator.clipboard.writeText(id);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      setCopiedId(null);
    }
  };

  const filteredSubmissions = submissions.filter((sub) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      sub.id.toLowerCase().includes(term) ||
      sub.language.toLowerCase().includes(term) ||
      (sub.filename && sub.filename.toLowerCase().includes(term)) ||
      (sub.requirement_ids && sub.requirement_ids.some((r) => r.toLowerCase().includes(term)))
    );
  });

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <History size={22} color="var(--primary-400)" />
              <span>Submission Repository</span>
            </h1>
            <p className="page-description">
              Audit trail of submitted source code artifacts with requirement mappings and test pipeline triggers.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              loading={refreshing}
              onClick={() => fetchSubmissions(skip, true)}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={Plus}
              onClick={() => navigate('/submissions/new')}
            >
              New Submission
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <Alert type="danger" title="Telemetry Error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card>
        {/* Table Search & Filter Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.75rem',
            marginBottom: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ position: 'relative', minWidth: '260px', flex: 1, maxWidth: '380px' }}>
            <Search
              size={14}
              style={{
                position: 'absolute',
                left: '0.65rem',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted)',
              }}
            />
            <input
              type="text"
              placeholder="Filter by ID, language, filename, or requirement..."
              className="form-input"
              style={{ paddingLeft: '2rem', fontSize: '0.8125rem' }}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            Total Ingested: <strong style={{ color: 'var(--text-primary)' }}>{total}</strong>
          </div>
        </div>

        {/* Submissions Table */}
        {loading ? (
          <LoadingSkeleton type="table" rows={6} cols={6} />
        ) : filteredSubmissions.length === 0 ? (
          <EmptyState
            icon={Code2}
            title={searchTerm ? 'No matching artifacts found' : 'Repository is empty'}
            description={
              searchTerm
                ? 'Try broadening your search query.'
                : 'No code artifacts have been submitted yet.'
            }
            action={
              !searchTerm && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <Button size="sm" variant="primary" onClick={() => navigate('/submissions/new')} icon={Plus}>
                    Submit Code Manually
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => navigate('/submissions/upload')} icon={Upload}>
                    Upload File
                  </Button>
                </div>
              )
            }
          />
        ) : (
          <>
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Submission ID</th>
                    <th>Language</th>
                    <th>Filename</th>
                    <th>Source Type</th>
                    <th>Requirements</th>
                    <th>Ingested At</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSubmissions.map((sub) => {
                    const sourceMeta = SUBMISSION_SOURCES[sub.source_type] || {
                      label: sub.source_type,
                      variant: 'secondary',
                    };

                    return (
                      <tr key={sub.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span className="text-mono" style={{ color: 'var(--primary-300)', fontWeight: 500 }}>
                              {truncateId(sub.id, 14)}
                            </span>
                            <button
                              type="button"
                              className="btn-copy-id"
                              onClick={() => handleCopy(sub.id)}
                              title="Copy ID"
                            >
                              {copiedId === sub.id ? (
                                <Check size={12} color="var(--status-passed)" />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                        </td>
                        <td>
                          <Badge variant="secondary">{sub.language}</Badge>
                        </td>
                        <td>
                          {sub.filename ? (
                            <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{sub.filename}</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>—</span>
                          )}
                        </td>
                        <td>
                          <Badge variant={sourceMeta.variant}>{sourceMeta.label}</Badge>
                        </td>
                        <td>
                          {sub.requirement_ids && sub.requirement_ids.length > 0 ? (
                            <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                              {sub.requirement_ids.slice(0, 2).map((r, i) => (
                                <Badge key={i} variant="accent" style={{ fontSize: '0.65rem' }}>
                                   {r}
                                </Badge>
                              ))}
                              {sub.requirement_ids.length > 2 && (
                                <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                                  +{sub.requirement_ids.length - 2}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>—</span>
                          )}
                        </td>
                        <td title={formatDate(sub.created_at)} style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                          <div>{formatRelativeTime(sub.created_at)}</div>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                            <Button
                              variant="outline"
                              size="sm"
                              className="btn-table-action"
                              icon={Eye}
                              onClick={() => setActiveSubmission(sub)}
                            >
                              View
                            </Button>
                            <Button
                              variant="primary"
                              size="sm"
                              className="btn-table-action"
                              icon={PlayCircle}
                              onClick={() => navigate(`/verifications?create_for=${encodeURIComponent(sub.id)}`)}
                            >
                              Verify
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <Pagination
              total={total}
              skip={skip}
              limit={limit}
              onPageChange={(newSkip) => fetchSubmissions(newSkip)}
            />
          </>
        )}
      </Card>

      {/* Submission Details Modal */}
      {activeSubmission && (
        <Modal
          isOpen={!!activeSubmission}
          onClose={() => setActiveSubmission(null)}
          title={`Artifact Details: ${activeSubmission.id}`}
          size="lg"
          footer={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const subId = activeSubmission.id;
                  setActiveSubmission(null);
                  navigate(`/verifications?submission_id=${encodeURIComponent(subId)}`);
                }}
              >
                View Linked Runs
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={PlayCircle}
                onClick={() => {
                  const subId = activeSubmission.id;
                  setActiveSubmission(null);
                  navigate(`/verifications?create_for=${encodeURIComponent(subId)}`);
                }}
              >
                Initiate Verification
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setActiveSubmission(null)}>
                Close
              </Button>
            </>
          }
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', marginBottom: '1rem', fontSize: '0.8125rem' }}>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Language
              </span>
              <div>
                <Badge variant="primary">{activeSubmission.language}</Badge>
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Filename
              </span>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                {activeSubmission.filename || 'None provided'}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Mechanism
              </span>
              <div>
                <Badge variant={SUBMISSION_SOURCES[activeSubmission.source_type]?.variant || 'secondary'}>
                  {SUBMISSION_SOURCES[activeSubmission.source_type]?.label || activeSubmission.source_type}
                </Badge>
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Submitted At
              </span>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {formatDate(activeSubmission.created_at)}
              </div>
            </div>
          </div>

          {activeSubmission.requirement_ids && activeSubmission.requirement_ids.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.3rem' }}>
                Linked Requirements
              </span>
              <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                {activeSubmission.requirement_ids.map((req, i) => (
                  <Badge key={i} variant="accent">
                    {req}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          <div>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Source Text Content:
            </span>
            <CodeViewer
              code={activeSubmission.code}
              language={activeSubmission.language}
              filename={activeSubmission.filename}
              maxHeight="380px"
            />
          </div>
        </Modal>
      )}
    </div>
  );
}
