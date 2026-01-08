/**
 * Data Quality Metrics and Deductions Formulas
 *
 * This file documents the logic used to calculate Data Quality scores and deductions.
 * These constants and formulas are used by the backend processing pipeline and can be used
 * by the frontend for tooltips or informational displays.
 */

export const DQ_DEDUCTIONS = {
  SCHEMA: {
    maxPoints: 40,
    label: "Schema Validation",
    description: "Validates that data matches the expected schema definition (required columns, data types).",
    formula: "Deduction = (Failed Checks / Total Checks) × 40",
    example: "If 1 out of 5 required columns is missing, deduction is (1/5) × 40 = 8 points."
  },
  FORMAT: {
    maxPoints: 35,
    label: "Format Parsing",
    description: "Validates that the file can be parsed correctly (e.g. valid CSV, lines match header).",
    formula: "Deduction = 35 points (if parsing fails completely)",
    example: "If the file cannot be parsed due to encoding errors, the full 35 points are deducted."
  },
  COMPLETENESS: {
    maxPoints: 20,
    label: "Completeness",
    description: "Validates that required fields contain non-null values.",
    formula: "Deduction = (Null Values in Required Fields / Total Required Values Checked) × 20",
    example: "If 10% of required field values are null, deduction is 0.10 × 20 = 2 points."
  },
  BOUNDS: {
    maxPoints: 15,
    label: "Bounds Range",
    description: "Validates that numeric/date values fall within specified min/max ranges from the schema.",
    formula: "Deduction = (Values Out of Bounds / Total Values Checked) × 15",
    example: "If 2 values out of 100 checked are outside the allowed range, deduction is (2/100) × 15 = 0.3 points."
  },
  UNIQUENESS: {
    maxPoints: 10,
    label: "Uniqueness",
    description: "Validates that fields designated as unique in the schema contain no duplicate values.",
    formula: "Deduction = (Duplicate Instances / Total Checks) × 10",
    example: "If 1 duplicate value is found in a unique column across 100 rows, deduction is (1/100) × 10 = 0.1 points."
  }
};
