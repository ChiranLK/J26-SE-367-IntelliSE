/**
 * Centralized language samples, default filenames, placeholders, and verification capabilities.
 * Supports all 10 selectable languages in the INTELISE Manual Entry submission workbench.
 */

export const LANGUAGE_FILENAMES = {
  python: 'sample.py',
  javascript: 'sample.js',
  typescript: 'sample.ts',
  java: 'Sample.java',
  cpp: 'sample.cpp',
  c: 'sample.c',
  csharp: 'Sample.cs',
  go: 'main.go',
  rust: 'main.rs',
  other: 'sample.txt',
};

export const LANGUAGE_SAMPLES = {
  python: `def calculate_metrics(data_points: list) -> dict:
    """Calculates summary statistics for telemetry data points."""
    if not data_points:
        return {"count": 0, "total": 0.0, "mean": 0.0}
    total = sum(data_points)
    mean = total / len(data_points)
    return {
        "count": len(data_points),
        "total": round(total, 2),
        "mean": round(mean, 2)
    }
`,

  javascript: `/**
 * Calculates summary metrics for an array of telemetry data points.
 * @param {number[]} dataPoints
 * @returns {{ count: number, total: number, mean: number }}
 */
export function calculateMetrics(dataPoints) {
  if (!Array.isArray(dataPoints) || dataPoints.length === 0) {
    return { count: 0, total: 0, mean: 0 };
  }
  const total = dataPoints.reduce((acc, val) => acc + val, 0);
  const mean = total / dataPoints.length;
  return {
    count: dataPoints.length,
    total: Number(total.toFixed(2)),
    mean: Number(mean.toFixed(2)),
  };
}
`,

  typescript: `interface MetricSummary {
  count: number;
  total: number;
  mean: number;
}

/**
 * Calculates summary metrics for numeric telemetry data points.
 */
export function calculateMetrics(dataPoints: number[]): MetricSummary {
  if (!dataPoints || dataPoints.length === 0) {
    return { count: 0, total: 0, mean: 0 };
  }
  const total = dataPoints.reduce((acc, val) => acc + val, 0);
  const mean = total / dataPoints.length;
  return {
    count: dataPoints.length,
    total: Math.round(total * 100) / 100,
    mean: Math.round(mean * 100) / 100,
  };
}
`,

  java: `import java.util.List;

public class Sample {
    public static class MetricSummary {
        public final int count;
        public final double total;
        public final double mean;

        public MetricSummary(int count, double total, double mean) {
            this.count = count;
            this.total = total;
            this.mean = mean;
        }
    }

    public static MetricSummary calculateMetrics(List<Double> dataPoints) {
        if (dataPoints == null || dataPoints.isEmpty()) {
            return new MetricSummary(0, 0.0, 0.0);
        }
        double total = 0.0;
        for (Double val : dataPoints) {
            total += (val != null ? val : 0.0);
        }
        double mean = total / dataPoints.size();
        return new MetricSummary(dataPoints.size(), total, mean);
    }
}
`,

  cpp: `#include <vector>
#include <numeric>

struct MetricSummary {
    int count;
    double total;
    double mean;
};

MetricSummary calculateMetrics(const std::vector<double>& dataPoints) {
    if (dataPoints.empty()) {
        return {0, 0.0, 0.0};
    }
    double total = std::accumulate(dataPoints.begin(), dataPoints.end(), 0.0);
    double mean = total / static_cast<double>(dataPoints.size());
    return {static_cast<int>(dataPoints.size()), total, mean};
}
`,

  c: `#include <stddef.h>

typedef struct {
    size_t count;
    double total;
    double mean;
} MetricSummary;

MetricSummary calculate_metrics(const double* data_points, size_t length) {
    MetricSummary summary = {0, 0.0, 0.0};
    if (data_points == NULL || length == 0) {
        return summary;
    }
    double total = 0.0;
    for (size_t i = 0; i < length; i++) {
        total += data_points[i];
    }
    summary.count = length;
    summary.total = total;
    summary.mean = total / (double)length;
    return summary;
}
`,

  csharp: `using System;
using System.Collections.Generic;
using System.Linq;

public class Sample
{
    public record MetricSummary(int Count, double Total, double Mean);

    public static MetricSummary CalculateMetrics(IEnumerable<double> dataPoints)
    {
        if (dataPoints == null || !dataPoints.Any())
        {
            return new MetricSummary(0, 0.0, 0.0);
        }
        double total = dataPoints.Sum();
        double mean = total / dataPoints.Count();
        return new MetricSummary(dataPoints.Count(), Math.Round(total, 2), Math.Round(mean, 2));
    }
}
`,

  go: `package main

type MetricSummary struct {
	Count int     \`json:"count"\`
	Total float64 \`json:"total"\`
	Mean  float64 \`json:"mean"\`
}

func CalculateMetrics(dataPoints []float64) MetricSummary {
	if len(dataPoints) == 0 {
		return MetricSummary{Count: 0, Total: 0.0, Mean: 0.0}
	}
	total := 0.0
	for _, val := range dataPoints {
		total += val
	}
	mean := total / float64(len(dataPoints))
	return MetricSummary{
		Count: len(dataPoints),
		Total: total,
		Mean:  mean,
	}
}
`,

  rust: `#[derive(Debug, PartialEq)]
pub struct MetricSummary {
    pub count: usize,
    pub total: f64,
    pub mean: f64,
}

pub fn calculate_metrics(data_points: &[f64]) -> MetricSummary {
    if data_points.is_empty() {
        return MetricSummary { count: 0, total: 0.0, mean: 0.0 };
    }
    let total: f64 = data_points.iter().sum();
    let mean = total / (data_points.len() as f64);
    MetricSummary {
        count: data_points.len(),
        total,
        mean,
    }
}
`,

  other: `# Sample plain text / configuration artifact
name=INTELISE_Module_Verification
version=1.0.0
target_environment=sandbox
metrics_enabled=true
threshold=0.95
`,
};

export const LANGUAGE_PLACEHOLDERS = {
  python: `# Paste Python source code here...\n\ndef verify_feature(payload: dict) -> bool:\n    return bool(payload and payload.get("status") == "ACTIVE")\n`,
  javascript: `// Paste JavaScript source code here...\n\nexport function verifyFeature(payload) {\n  return Boolean(payload && payload.status === 'ACTIVE');\n}\n`,
  typescript: `// Paste TypeScript source code here...\n\nexport function verifyFeature(payload: Record<string, unknown>): boolean {\n  return Boolean(payload && payload.status === 'ACTIVE');\n}\n`,
  java: `// Paste Java source code here...\n\npublic class Sample {\n    public static boolean verifyFeature() {\n        return true;\n    }\n}\n`,
  cpp: `// Paste C++ source code here...\n\nbool verifyFeature() {\n    return true;\n}\n`,
  c: `// Paste C source code here...\n\nint verify_feature() {\n    return 1;\n}\n`,
  csharp: `// Paste C# source code here...\n\npublic class Sample {\n    public static bool VerifyFeature() => true;\n}\n`,
  go: `// Paste Go source code here...\n\npackage main\n\nfunc VerifyFeature() bool {\n    return true;\n}\n`,
  rust: `// Paste Rust source code here...\n\npub fn verify_feature() -> bool {\n    true\n}\n`,
  other: `# Paste raw artifact text or configuration here...\n`,
};

export const LANGUAGE_CAPABILITIES = {
  python: {
    tier: 'FULL_SANDBOX_VERIFICATION',
    label: 'Full Execution Tier',
    badgeVariant: 'success',
    description: 'Docker container runner, isolated pytest test suites, defect localization, and post-delivery XAI fully operational.',
    isExecutionSupported: true,
  },
  javascript: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires Node.js sandbox runner.',
    isExecutionSupported: false,
  },
  typescript: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires Node.js/TS sandbox runner.',
    isExecutionSupported: false,
  },
  java: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires JDK sandbox runner.',
    isExecutionSupported: false,
  },
  cpp: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires GCC/Clang sandbox runner.',
    isExecutionSupported: false,
  },
  c: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires GCC sandbox runner.',
    isExecutionSupported: false,
  },
  csharp: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires .NET sandbox runner.',
    isExecutionSupported: false,
  },
  go: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires Go sandbox runner.',
    isExecutionSupported: false,
  },
  rust: {
    tier: 'INGESTION_AND_STATIC_ANALYSIS',
    label: 'Ingestion & Static Tier',
    badgeVariant: 'secondary',
    description: 'Source ingestion, syntax validation, and LLM review supported. Isolated test execution requires Cargo/rustc sandbox runner.',
    isExecutionSupported: false,
  },
  other: {
    tier: 'PLAIN_TEXT_INGESTION',
    label: 'Text Ingestion Tier',
    badgeVariant: 'secondary',
    description: 'Plain text / configuration artifact ingestion and hash verification supported.',
    isExecutionSupported: false,
  },
};

export function getLanguageSample(languageKey) {
  const key = (languageKey || '').toLowerCase();
  return LANGUAGE_SAMPLES[key] || LANGUAGE_SAMPLES.python;
}

export function getLanguageFilename(languageKey) {
  const key = (languageKey || '').toLowerCase();
  return LANGUAGE_FILENAMES[key] || 'sample.py';
}

export function getLanguagePlaceholder(languageKey) {
  const key = (languageKey || '').toLowerCase();
  return LANGUAGE_PLACEHOLDERS[key] || LANGUAGE_PLACEHOLDERS.python;
}

export function getLanguageCapability(languageKey) {
  const key = (languageKey || '').toLowerCase();
  return LANGUAGE_CAPABILITIES[key] || LANGUAGE_CAPABILITIES.other;
}
