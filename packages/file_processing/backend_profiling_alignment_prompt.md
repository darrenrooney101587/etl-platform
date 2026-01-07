# Backend Data Profiling Alignment Directive

## Context
The frontend `DataProfilingSection.tsx` component expects data profiling results in a specific format to render statistics, completeness, uniqueness, and value distributions correctly. Currently, there is a drift between the backend output (specifically the dictionary/map format) and the array-based format the frontend is optimized for. Additionally, key metric names (e.g., `mean` vs `avg`, `stdDev` vs `std_dev`) need to be standardized.

## Goal
Update the backend data profiling logic (likely in `bms_reporting` or related data processing services) to produce JSON structures that strictly match the TypeScript interfaces defined below.

## Expected JSON Output Structures

The `MonitoringFileDataProfile` model should store these JSON objects in their respective fields.

### 1. Statistical Summary (`statistical_summary`)
**Frontend Expectation:** An **array of objects**, where each object represents a numeric column's stats.
**Key Requirements:**
- Types: `mean`, `median`, `min`, `max`, `stdDev` should be numbers (float/int).
- `outlierValues` should be an array of numbers.
- `distribution` should be a string ('normal', 'skewed-left', 'skewed-right', 'uniform', 'bimodal').

**Target Schema:**
```json
[
  {
    "column": "age",
    "mean": 35.5,
    "median": 34.0,
    "stdDev": 12.1,
    "min": 18,
    "max": 85,
    "count": 1000,
    "zeros": 0,
    "negatives": 0,
    "iqr": 15.0,
    "distribution": "normal",  // one of: 'normal', 'skewed-left', 'skewed-right', 'uniform', 'bimodal'
    "outlierCount": 2,
    "outlierValues": [85, 18]
  },
  ...
]
```

### 2. Completeness Overview (`completeness_overview`)
**Frontend Expectation:** An object containing summary stats and a lists of columns with specific null counts.

**Target Schema:**
```json
{
  "totalRows": 1921,
  "completeRows": 1800,
  "completeRowPercentage": 93.7,
  "entirelyNullColumns": ["deprecated_col"],
  "columnsWithNulls": [
    {
      "column": "mid_name",
      "nulls": 386,
      "nullPercentage": 20.1
    }
  ]
}
```

### 3. Uniqueness Overview (`uniqueness_overview`)
**Frontend Expectation:** An object containing duplicate row counts and per-column cardinality.

**Target Schema:**
```json
{
  "totalRows": 1921,
  "uniqueRows": 1921,
  "duplicateRows": 0,
  "duplicatePercentage": 0.0,
  "columns": [
    {
      "column": "email",
      "uniqueCount": 1119,
      "cardinality": 58.25 // percent (0-100) or ratio (0-1) depending on frontend logic (Frontend expects 0-100 usually)
    },
    {
      "column": "officer_id",
      "uniqueCount": 1921,
      "cardinality": 100.0
    }
  ]
}
```

### 4. Value Distributions (`value_distributions`)
**Frontend Expectation:** An **array of objects** per column, each containing a histogram.

**Target Schema:**
```json
[
  {
    "column": "race",
    "histogram": [
      { "bin": "White", "count": 1793 },
      { "bin": "Black", "count": 45 },
      { "bin": "Asian", "count": 13 }
    ]
  },
  {
    "column": "gender",
    "histogram": [
      { "bin": "M", "count": 1659 },
      { "bin": "F", "count": 262 }
    ]
  }
]
```

### 5. Type & Format Issues (`type_format_issues`)
**Frontend Expectation:** An **array of issue objects**.

**Target Schema:**
```json
[
  {
    "column": "birth_date",
    "expectedType": "date",
    "actualType": "string",
    "invalidCount": 5,
    "invalidPercentage": 0.26,
    "sampleInvalid": ["00/00/0000", "Not Available"]
  }
]
```

### 6. Bounds & Anomalies (`bounds_anomalies`)
**Frontend Expectation:** An **array of anomaly objects**.

**Target Schema:**
```json
[
  {
    "column": "salary",
    "severity": "High",
    "lowerBound": 30000,
    "upperBound": 150000,
    "outliersCount": 3,
    "exampleValues": [950000, 500]
  }
]
```

## Action Items
1.  Refactor the backend profiling service to calculate these specific metrics.
2.  Ensure key casing matches (camelCase is preferred for JSON payloads, though the frontend has some fallback logic).
3.  Ensure numeric values are actual numbers (floats/ints), not strings, to avoid 'N/A' display in the frontend.
4.  Populate `stdDev`, `mean`, `median` for all numeric columns.
5.  Populate `histogram` arrays for categorical columns.
