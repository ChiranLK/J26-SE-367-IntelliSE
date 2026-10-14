import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import Button from './Button';

export default function Pagination({
  total = 0,
  skip = 0,
  limit = 10,
  onPageChange,
  className = '',
}) {
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const hasPrev = skip > 0;
  const hasNext = skip + limit < total;

  const handlePrev = () => {
    if (hasPrev) {
      onPageChange(Math.max(0, skip - limit));
    }
  };

  const handleNext = () => {
    if (hasNext) {
      onPageChange(skip + limit);
    }
  };

  return (
    <div className={`pagination ${className}`.trim()}>
      <div className="pagination-info">
        Showing{' '}
        <span className="pagination-info-number">
          {total === 0 ? 0 : skip + 1}
        </span>{' '}
        to{' '}
        <span className="pagination-info-number">
          {Math.min(skip + limit, total)}
        </span>{' '}
        of{' '}
        <span className="pagination-info-number">{total}</span> entries
      </div>
      <div className="pagination-controls">
        <Button
          variant="outline"
          size="sm"
          disabled={!hasPrev}
          onClick={handlePrev}
          icon={ChevronLeft}
          className="btn-pagination"
        >
          Previous
        </Button>
        <span className="pagination-page-indicator">
          Page {currentPage} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasNext}
          onClick={handleNext}
          iconRight={ChevronRight}
          className="btn-pagination"
        >
          Next
        </Button>
      </div>
    </div>
  );
}
