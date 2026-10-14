import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import StatCard from '../components/common/StatCard';
import EmptyState from '../components/common/EmptyState';
import CodeViewer from '../components/common/CodeViewer';
import Pagination from '../components/common/Pagination';

describe('Common Components', () => {
  it('renders Badge with correct variant class', () => {
    const { container } = render(<Badge variant="success">Passed</Badge>);
    expect(screen.getByText('Passed')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('badge-success');
  });

  it('renders Button and handles click events', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click Me</Button>);
    const btn = screen.getByRole('button', { name: /click me/i });
    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('disables Button when loading or disabled is true', () => {
    render(<Button loading>Loading...</Button>);
    const btn = screen.getByRole('button', { name: /loading/i });
    expect(btn).toBeDisabled();
  });

  it('renders Card with title, subtitle, and content', () => {
    render(
      <Card title="Test Card" subtitle="Subtitle here">
        <div>Card Content</div>
      </Card>
    );
    expect(screen.getByText('Test Card')).toBeInTheDocument();
    expect(screen.getByText('Subtitle here')).toBeInTheDocument();
    expect(screen.getByText('Card Content')).toBeInTheDocument();
  });

  it('renders StatCard with metric values', () => {
    render(
      <StatCard
        title="Submissions"
        value="42"
        description="Total items stored"
      />
    );
    expect(screen.getByText('Submissions')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Total items stored')).toBeInTheDocument();
  });

  it('renders EmptyState with action', () => {
    render(
      <EmptyState
        title="No items found"
        description="Please add something."
        action={<button>Add Now</button>}
      />
    );
    expect(screen.getByText('No items found')).toBeInTheDocument();
    expect(screen.getByText('Please add something.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add now/i })).toBeInTheDocument();
  });

  it('renders CodeViewer safely as plain text inside code tag', () => {
    const sampleCode = `def hello():\n    return "world"`;
    render(<CodeViewer code={sampleCode} language="python" filename="test.py" />);
    expect(screen.getByText('test.py')).toBeInTheDocument();
    expect(screen.getByText('def hello():')).toBeInTheDocument();
    expect(screen.getByText('return "world"')).toBeInTheDocument();
  });

  it('renders Pagination and triggers page navigation', () => {
    const handlePageChange = vi.fn();
    render(
      <Pagination
        total={30}
        skip={10}
        limit={10}
        onPageChange={handlePageChange}
      />
    );
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    const nextBtn = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextBtn);
    expect(handlePageChange).toHaveBeenCalledWith(20);
  });
});
