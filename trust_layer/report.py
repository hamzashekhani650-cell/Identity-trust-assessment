
from trust_layer.record import PatientRecord


DOH_CLAUSE_MAP = {
    "completeness": "DP-DA-05 (accuracy assessment) / DP-PDC-01 (processing documentation)",
    "temporal":     "Section 1.4.2 (integrity) / DP-DA-04 (correctness)",
    "identity":     "DP-DA-02 (identity validation before access)",
    "provenance":   "DP-IS-02 / DP-IS-03 (system ownership) / DP-DA-06 (third-party agreements)",
    "cross_record": "DP-RM-01 / DP-RM-02 / DP-RM-03 (ongoing privacy risk assessment)",
}


def generate_decision_report(record, dimensions, score, decision, weights=None):
    """
    Produce a human-readable HTML report explaining a trust decision.
    Every dimension score is traced to its DOH regulatory clause.
    """
    if weights is None:
        weights = {
            "completeness": 0.20, "temporal": 0.15,
            "identity": 0.20, "provenance": 0.15, "cross_record": 0.30,
        }

    flagged_dims = [d for d, v in dimensions.items() if v < 0.8]
    if not flagged_dims:
        flagged_dims = ["(none)"]

    rows_html = ""
    for dim, value in dimensions.items():
        clause = DOH_CLAUSE_MAP.get(dim, "unknown")
        color = "#2E7D32" if value >= 0.8 else ("#F59E0B" if value >= 0.5 else "#C62828")
        rows_html += (
            f"<tr>"
            f"<td>{dim}</td>"
            f"<td style='text-align:center'>{value:.2f}</td>"
            f"<td style='text-align:center'>{weights[dim]:.2f}</td>"
            f"<td><span style='color:{color};font-weight:bold'>{clause}</span></td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Identity Trust Decision Report</title>
<style>
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; margin: 40px; color: #1F3A5F; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #1F3A5F; padding-bottom: 8px; }}
  h2 {{ font-size: 16px; margin-top: 30px; color: #4A6FA5; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
  th, td {{ border: 1px solid #D1D5DB; padding: 8px 12px; text-align: left; }}
  th {{ background: #F3F4F6; }}
  .decision {{ font-size: 18px; font-weight: bold; padding: 12px; border-radius: 6px; margin-top: 10px; }}
  .meta {{ color: #6B7280; font-size: 12px; }}
</style>
</head>
<body>
  <h1>Identity Trust Decision Report</h1>
  <p class="meta">Generated at decision time. Every dimension traces to a DOH Standard clause.</p>

  <h2>Record</h2>
  <table>
    <tr><th>Canonical ID</th><td>{record.canonical_id or "(unset)"}</td></tr>
    <tr><th>Name</th><td>{record.given_name} {record.family_name}</td></tr>
    <tr><th>Date of Birth</th><td>{record.date_of_birth}</td></tr>
    <tr><th>Identifier Present</th><td>{"yes" if record.emirates_id else "no"}</td></tr>
    <tr><th>Source Facility</th><td>{record.source_facility or "(unset)"}</td></tr>
  </table>

  <h2>Dimension Breakdown</h2>
  <table>
    <tr><th>Dimension</th><th>Score</th><th>Weight</th><th>DOH Clause</th></tr>
    {rows_html}
  </table>

  <h2>Composite Score</h2>
  <p style="font-size:32px;font-weight:bold;margin:10px 0">{score:.4f}</p>
  <div class="decision" style="background:#FEF3C7">{decision}</div>

  <h2>Flagged Dimensions</h2>
  <p>{", ".join(flagged_dims)}</p>

  <h2>Regulatory Audit Trail</h2>
  <p>This decision is recorded in the tamper-evident audit log. Any subsequent modification of the log is detectable through the hash-chain verification.</p>
</body>
</html>
"""
    return html


def save_decision_report(record, dimensions, score, decision, path="decision_report.html"):
    html = generate_decision_report(record, dimensions, score, decision)
    with open(path, "w") as f:
        f.write(html)
    return path
