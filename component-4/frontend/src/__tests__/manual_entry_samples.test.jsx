import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ManualSubmissionPage from '../pages/ManualSubmissionPage';
import { PROGRAMMING_LANGUAGES } from '../utils/constants';
import {
  LANGUAGE_FILENAMES,
  LANGUAGE_SAMPLES,
  getLanguageSample,
  getLanguageFilename,
} from '../utils/languageSamples';

function renderComponent() {
  return render(
    <MemoryRouter>
      <ManualSubmissionPage />
    </MemoryRouter>
  );
}

describe('Manual Entry Language-Aware Sample Loading (Task 1)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('verifies language sample and filename mapping exists for all 10 supported languages', () => {
    PROGRAMMING_LANGUAGES.forEach((lang) => {
      const sample = getLanguageSample(lang.value);
      const filename = getLanguageFilename(lang.value);
      expect(sample).toBeDefined();
      expect(sample.length).toBeGreaterThan(10);
      expect(filename).toBe(LANGUAGE_FILENAMES[lang.value]);
    });
  });

  it('loads the correct sample and filename for every selectable language in the dropdown', () => {
    renderComponent();

    const select = screen.getByLabelText(/Programming Language \*/i);
    const loadSampleBtn = screen.getByRole('button', { name: /Load Sample/i });
    const editor = screen.getByLabelText(/Source Code \*/i);
    const filenameInput = screen.getByLabelText(/Filename \(Optional\)/i);

    PROGRAMMING_LANGUAGES.forEach((lang) => {
      // 1. Select the language from the dropdown
      fireEvent.change(select, { target: { value: lang.value } });
      expect(select.value).toBe(lang.value);

      // 2. Click "Load Sample"
      fireEvent.click(loadSampleBtn);

      // 3. Verify editor contains the exact language sample
      const expectedSample = LANGUAGE_SAMPLES[lang.value];
      expect(editor.value).toBe(expectedSample);

      // 4. Verify filename matches the expected filename
      const expectedFilename = LANGUAGE_FILENAMES[lang.value];
      expect(filenameInput.value).toBe(expectedFilename);
    });
  });

  it('does NOT overwrite user-written code merely by changing the language dropdown', () => {
    renderComponent();

    const select = screen.getByLabelText(/Programming Language \*/i);
    const editor = screen.getByLabelText(/Source Code \*/i);

    // User types custom code in Python
    const userCode = '// Custom user implementation code\nconst x = 42;';
    fireEvent.change(editor, { target: { value: userCode } });
    expect(editor.value).toBe(userCode);

    // Switch language to Java
    fireEvent.change(select, { target: { value: 'java' } });
    expect(select.value).toBe('java');

    // Code MUST remain unchanged
    expect(editor.value).toBe(userCode);

    // Switch language to Rust
    fireEvent.change(select, { target: { value: 'rust' } });
    expect(select.value).toBe('rust');

    // Code MUST still remain unchanged
    expect(editor.value).toBe(userCode);
  });

  it('protects custom user code from destructive replacement when Load Sample is cancelled', () => {
    renderComponent();

    const select = screen.getByLabelText(/Programming Language \*/i);
    const loadSampleBtn = screen.getByRole('button', { name: /Load Sample/i });
    const editor = screen.getByLabelText(/Source Code \*/i);

    const userCode = 'def my_custom_algorithm():\n    return 12345';
    fireEvent.change(editor, { target: { value: userCode } });

    // Mock confirm dialog returning FALSE (User cancels replacement)
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    fireEvent.change(select, { target: { value: 'go' } });
    fireEvent.click(loadSampleBtn);

    expect(confirmSpy).toHaveBeenCalled();
    // Editor code must be preserved because user cancelled
    expect(editor.value).toBe(userCode);
  });

  it('allows replacing custom code with sample when confirmation is accepted', () => {
    renderComponent();

    const select = screen.getByLabelText(/Programming Language \*/i);
    const loadSampleBtn = screen.getByRole('button', { name: /Load Sample/i });
    const editor = screen.getByLabelText(/Source Code \*/i);
    const filenameInput = screen.getByLabelText(/Filename \(Optional\)/i);

    const userCode = 'custom code to be overwritten';
    fireEvent.change(editor, { target: { value: userCode } });

    // Mock confirm dialog returning TRUE (User accepts replacement)
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    fireEvent.change(select, { target: { value: 'java' } });
    fireEvent.click(loadSampleBtn);

    expect(confirmSpy).toHaveBeenCalled();
    expect(editor.value).toBe(LANGUAGE_SAMPLES.java);
    expect(filenameInput.value).toBe('Sample.java');
  });

  it('displays appropriate execution tier badges and capability descriptions', () => {
    renderComponent();

    const select = screen.getByLabelText(/Programming Language \*/i);

    // Python -> Full Execution Tier
    fireEvent.change(select, { target: { value: 'python' } });
    expect(screen.getByText('Full Execution Tier')).toBeInTheDocument();
    expect(screen.getByText(/Docker container runner, isolated pytest test suites/i)).toBeInTheDocument();

    // Java -> Ingestion & Static Tier
    fireEvent.change(select, { target: { value: 'java' } });
    expect(screen.getByText('Ingestion & Static Tier')).toBeInTheDocument();
    expect(screen.getByText(/requires JDK sandbox runner/i)).toBeInTheDocument();

    // Rust -> Ingestion & Static Tier
    fireEvent.change(select, { target: { value: 'rust' } });
    expect(screen.getByText(/requires Cargo\/rustc sandbox runner/i)).toBeInTheDocument();
  });
});
