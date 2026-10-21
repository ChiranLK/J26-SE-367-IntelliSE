import React from 'react';
import { Sparkles } from 'lucide-react';

export default function GenerationIndicator() {
  return (
    <div className="xai-generating" role="status" aria-live="polite">
      <div className="xai-generating-orb" aria-hidden="true">
        <Sparkles size={20} />
      </div>

      <div className="xai-generating-copy">
        <div className="xai-generating-title">
          <span>Generating software explanation</span>
          <span className="xai-generating-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </div>
        <div className="xai-generating-detail">
          Grounding the response in verified source structure and passed-test evidence
        </div>
      </div>

      <div className="xai-generating-track" aria-hidden="true">
        <span />
      </div>
    </div>
  );
}
