# Understanding Signals vs Signal Groups (Concrete Example)

This document explains **Signals** and **Signal Groups** using a concrete CloverDX-style example.
It is intended for engineers and technical stakeholders.

---

## One-Sentence Definition

- **Signal** = one occurrence (one job run failing, one alert firing)
- **Signal Group** = one underlying problem that may occur many times

> Humans work Signal Groups.  
> Systems emit Signals.

---

## Example Scenario

### System
- Platform: **CloverDX**
- Total tenants: **30**
- Tenants with errors today: **5**
- One of those tenants has **2 different errors**

---

## Step 1: List the raw Signals

Each failed job run produces **one Signal**.

### Tenant A
- Job `load_arrests` failed (DB timeout)
- Job `load_arrests` failed again later (DB timeout)

### Tenant B
- Job `load_incidents` failed (S3 permission denied)

### Tenant C
- Job `load_cases` failed (schema mismatch)

### Tenant D
- Job `load_cases` failed (schema mismatch)

### Tenant E
- Job `load_cases` failed (schema mismatch)
- Job `load_officers` failed (missing input file)

**Total Signals:** 7

---

## Step 2: Fingerprinting (how grouping works)

Each Signal is fingerprinted using stable attributes:

```
fingerprint = hash(
  tenant_id +
  job_name +
  signal_type +
  error_class +
  normalized_error_message +
  stage
)
```

Signals with the **same fingerprint** belong to the **same Signal Group**.

---

## Step 3: Signal Groups (the key concept)

Now we collapse repeated Signals into Signal Groups.

### Tenant A
- Same tenant
- Same job
- Same error (DB timeout)

➡ **1 Signal Group**
- Occurrences: 2

---

### Tenant B
- One failure type

➡ **1 Signal Group**
- Occurrences: 1

---

### Tenant C
- One failure type

➡ **1 Signal Group**
- Occurrences: 1

---

### Tenant D
- Same error type as Tenant C
- **Different tenant**

➡ **1 Signal Group**
- Occurrences: 1

---

### Tenant E
- Two different failures

➡ **2 Signal Groups**
- `load_cases` schema mismatch
- `load_officers` missing file

---

## Final Breakdown

| Tenant | Signals (Occurrences) | Signal Groups |
|------|------------------------|---------------|
| A    | 2                      | 1             |
| B    | 1                      | 1             |
| C    | 1                      | 1             |
| D    | 1                      | 1             |
| E    | 2                      | 2             |
| **Total** | **7**              | **6 Signal Groups** |

---

## What a Signal Group Represents

A Signal Group corresponds to **one thing a human needs to think about**.

Example:

```
Tenant: A
Job: load_arrests
Problem: Database timeout during write stage
Status: Open
First seen: 2026-01-07 01:14
Last seen: 2026-01-09 03:42
Occurrences: 14
Severity: S1
Assigned to: Darren
```

Even though it happened 14 times, this is **one problem**.

---

## Why This Matters

Without Signal Groups:
- Every failure posts to Slack
- Repeated daily issues spam channels
- Engineers stop paying attention

With Signal Groups:
- One Slack message per underlying problem
- Repeats only update counts and timestamps
- Ownership and acknowledgement are tracked
- Long-running issues remain visible without noise

---

## Common Misunderstandings

### “Is a Signal Group per tenant?”
No.

### “Is a Signal Group per job?”
No.

### “Is a Signal Group global across tenants?”
No.

A Signal Group is:
> **Per tenant + per job + per underlying failure type**

---

## Mental Model

- Signals are events.
- Signal Groups are problems.
- Notifications page is the work queue.
- Slack is for awareness and quick actions.
