// Turns raw FHIR resources into a small payer-agnostic shape your app owns.
// Field paths follow the CARIN Blue Button EOB profile; payers vary, so every
// access is defensive. Extend as you see real data.

const money = (a) => (a && typeof a.value === "number" ? a.value : null);

export function normalizeCoverage(resources) {
  return resources
    .filter((r) => r.resourceType === "Coverage")
    .map((c) => ({
      id: c.id,
      status: c.status,
      type: c.type?.coding?.[0]?.display ?? c.class?.[0]?.name ?? null,
      period: c.period ?? null,
    }));
}

export function normalizeEob(resources) {
  return resources
    .filter((r) => r.resourceType === "ExplanationOfBenefit")
    .map((e) => {
      const totals = Object.fromEntries(
        (e.total || []).map((t) => [t.category?.coding?.[0]?.code, money(t.amount)])
      );
      return {
        id: e.id,
        type: e.type?.coding?.[0]?.display ?? null,
        serviceStart: e.billablePeriod?.start ?? null,
        serviceEnd: e.billablePeriod?.end ?? null,
        provider: e.provider?.display ?? null,
        submitted: totals.submitted ?? null,
        planPaid: money(e.payment?.amount),
        // Often absent or inconsistent across payers; treat as best-effort.
        memberResponsibility: totals.memberliability ?? null,
      };
    });
}

// Rough year-to-date spend rollup. NOT a substitute for a real deductible/OOP
// accumulator; use plan docs (SBC) or a 271 / voice call for that.
export function ytdSummary(eobs, year = new Date().getFullYear()) {
  const inYear = eobs.filter((e) => e.serviceStart?.startsWith(String(year)));
  const sum = (k) => inYear.reduce((s, e) => s + (e[k] || 0), 0);
  return {
    year,
    claimCount: inYear.length,
    submitted: sum("submitted"),
    planPaid: sum("planPaid"),
    memberResponsibility: sum("memberResponsibility"),
  };
}
