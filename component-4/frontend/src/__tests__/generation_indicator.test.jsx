import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import GenerationIndicator from '../components/common/GenerationIndicator';

describe('GenerationIndicator', () => {
  it('announces the evidence-grounded post-delivery generation state', () => {
    render(<GenerationIndicator />);

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent('Generating software explanation');
    expect(status).toHaveTextContent('verified source structure and passed-test evidence');
  });
});
