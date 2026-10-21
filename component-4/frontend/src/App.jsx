import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import UnifiedSubmissionPage from './pages/UnifiedSubmissionPage';
import SubmissionHistoryPage from './pages/SubmissionHistoryPage';
import VerificationRunsPage from './pages/VerificationRunsPage';
import DefectReportsPage from './pages/DefectReportsPage';
import XaiExplanationsPage from './pages/XaiExplanationsPage';
import FeedbackHistoryPage from './pages/FeedbackHistoryPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="submissions">
            <Route index element={<SubmissionHistoryPage />} />
            <Route path="new" element={<UnifiedSubmissionPage />} />
            <Route path="upload" element={<UnifiedSubmissionPage />} />
          </Route>
          <Route path="verifications" element={<VerificationRunsPage />} />
          <Route path="defects" element={<DefectReportsPage />} />
          <Route path="xai" element={<XaiExplanationsPage />} />
          <Route path="feedback" element={<FeedbackHistoryPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
