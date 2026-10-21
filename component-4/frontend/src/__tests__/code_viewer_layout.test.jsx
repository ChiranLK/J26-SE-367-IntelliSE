import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import CodeViewer from '../components/common/CodeViewer';
import ProjectFileTree from '../components/common/ProjectFileTree';
import UnifiedSubmissionPage from '../pages/UnifiedSubmissionPage';
import * as submissionApi from '../api/submissionApi';

vi.mock('../api/submissionApi', () => ({
  submitCode: vi.fn(),
  uploadSourceFile: vi.fn(),
}));

describe('Multi-File Code Viewer & Project Tree Layout (Issue 1, 2, 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Issue 1 & 3: CodeViewer Scrolling, Formatting & Complete Copying', () => {
    const longCodeSample = `def calculate_subtotal(prices: list[float]) -> float:
    """Return the sum of non-negative item prices."""
    if any(price < 0 for price in prices):
        raise ValueError("prices must be non-negative")
    return round(sum(prices), 2)

# Long line to verify that lines do not wrap by default and support horizontal scrolling
def very_long_function_signature_with_many_parameters_for_demonstration_purposes(first_argument_price: float, second_argument_discount: float, third_argument_tax: float, fourth_argument_shipping: float) -> dict[str, float]:
    return {"total": first_argument_price - second_argument_discount + third_argument_tax + fourth_argument_shipping}
`;

    it('renders CodeViewer header with filename, badge, line count, wrap button, and copy button', () => {
      render(
        <CodeViewer
          code={longCodeSample}
          language="python"
          filename="shop/pricing.py"
        />
      );

      expect(screen.getByText('shop/pricing.py')).toBeInTheDocument();
      expect(screen.getByText('python')).toBeInTheDocument();
      expect(screen.getByText('(10 lines)')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /enable line wrap/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /copy code to clipboard/i })).toBeInTheDocument();
    });

    it('preserves code indentation and default nowrap pre formatting', () => {
      const { container } = render(
        <CodeViewer
          code={longCodeSample}
          language="python"
          filename="shop/pricing.py"
        />
      );

      const body = container.querySelector('.code-viewer-body');
      expect(body).toHaveClass('nowrap-lines');
      expect(body).not.toHaveClass('wrap-lines');

      // Toggling wrap button switches to wrap-lines
      const wrapBtn = screen.getByRole('button', { name: /enable line wrap/i });
      fireEvent.click(wrapBtn);
      expect(body).toHaveClass('wrap-lines');

      // Toggling again returns to nowrap-lines
      const unwrapBtn = screen.getByRole('button', { name: /disable line wrap/i });
      fireEvent.click(unwrapBtn);
      expect(body).toHaveClass('nowrap-lines');
    });

    it('copies complete source content, not just visible lines', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      render(
        <CodeViewer
          code={longCodeSample}
          language="python"
          filename="shop/pricing.py"
        />
      );

      const copyBtn = screen.getByRole('button', { name: /copy code to clipboard/i });
      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(writeTextMock).toHaveBeenCalledWith(longCodeSample);
      });

      expect(screen.getByText('Copied')).toBeInTheDocument();
    });
  });

  describe('Issue 2: ProjectFileTree Hierarchy, Scrolling & File Selection', () => {
    const mockFiles = {
      'shop/__init__.py': '# shop module\n',
      'shop/checkout.py': 'def checkout(): pass\n',
      'shop/pricing.py': 'def calculate(): pass\n',
      'tests/integration/test_integration_checkout.py': 'def test_checkout(): pass\n',
      'tests/performance/test_performance_checkout.py': 'def test_perf(): pass\n',
      'tests/unit/test_unit_pricing.py': 'def test_pricing(): pass\n',
    };

    it('renders file tree with expandable folders and allows file selection', () => {
      const handleSelectFile = vi.fn();
      render(
        <ProjectFileTree
          files={mockFiles}
          selectedFile="shop/pricing.py"
          onSelectFile={handleSelectFile}
          entrypoint="shop/pricing.py"
        />
      );

      expect(screen.getByText('Project Tree (6 files)')).toBeInTheDocument();
      expect(screen.getByText('pricing.py')).toBeInTheDocument();
      expect(screen.getByText('entry')).toBeInTheDocument();

      // Click another file to select
      const checkoutFile = screen.getByText('checkout.py');
      fireEvent.click(checkoutFile);
      expect(handleSelectFile).toHaveBeenCalledWith('shop/checkout.py');

      // Toggle folder collapsing
      const shopFolder = screen.getByText('shop');
      fireEvent.click(shopFolder);
      // After collapsing, files inside shop are hidden
      expect(screen.queryByText('checkout.py')).not.toBeInTheDocument();

      // Expand folder again
      fireEvent.click(shopFolder);
      expect(screen.getByText('checkout.py')).toBeInTheDocument();
    });
  });

  describe('Multi-File Two-Panel Layout & Selection Update in UnifiedSubmissionPage', () => {
    it('updates CodeViewer when a different file is clicked in the ProjectFileTree', async () => {
      const mockProjectFiles = {
        'shop/pricing.py': '# Pricing logic\ndef price(): return 100\n',
        'shop/checkout.py': '# Checkout logic\ndef process(): return True\n',
        'tests/unit/test_unit_pricing.py': '# Test unit\ndef test(): assert True\n',
      };

      submissionApi.uploadSourceFile.mockResolvedValueOnce({
        id: 'sub-friday-demo',
        filename: 'friday_defective_three_tests.zip',
        language: 'python',
        created_at: '2026-10-21T09:00:00Z',
        metadata: {
          is_multi_file: true,
          total_project_files: 3,
          entrypoint: 'shop/pricing.py',
          project_files: mockProjectFiles,
        },
      });

      const { container } = render(
        <MemoryRouter initialEntries={['/submissions/new']}>
          <Routes>
            <Route path="/submissions/new" element={<UnifiedSubmissionPage />} />
          </Routes>
        </MemoryRouter>
      );

      const zipInput = container.querySelector('input[type="file"][accept=".zip"]');
      const zipFile = new File(['mockzip'], 'friday_defective_three_tests.zip', { type: 'application/zip' });
      fireEvent.change(zipInput, { target: { files: [zipFile] } });

      const submitBtn = screen.getByRole('button', { name: /upload project/i });
      fireEvent.click(submitBtn);

      // Verify the two-panel layout container is rendered
      await waitFor(() => {
        expect(container.querySelector('.submission-success-project-grid')).not.toBeNull();
      });

      expect(container.querySelector('.submission-project-tree-panel')).not.toBeNull();
      expect(container.querySelector('.submission-project-code-panel')).not.toBeNull();

      // Initial active file is entrypoint: shop/pricing.py
      expect(screen.getByText('Pricing logic', { exact: false })).toBeInTheDocument();

      // Copy button is present and accessible in the header
      const copyBtn = screen.getByRole('button', { name: /copy code to clipboard/i });
      expect(copyBtn).toBeInTheDocument();

      // Click on shop/checkout.py in the file tree
      const checkoutFileItem = screen.getByText('checkout.py');
      fireEvent.click(checkoutFileItem);

      // CodeViewer should now display checkout.py content
      await waitFor(() => {
        expect(screen.getByText('Checkout logic', { exact: false })).toBeInTheDocument();
      });
    });
  });
});
