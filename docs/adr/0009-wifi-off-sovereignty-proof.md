# Wi-Fi-off sovereignty demo

Strong proof would be firewall-deny plus packet capture plus an `--offline` flag plus weight hashes, but the venue demo opts for simply turning Wi-Fi off and showing the workbench still works. We accept this weak proof for this milestone as a deliberate trade-off for demo simplicity; PSU and defence reviewers will likely demand the strong variant later.

## Consequences

- Evaluators see continuity without network, not a verifiable absence of external calls (cached, localhost, and telemetry paths stay unproven).
- Revisit with deny-egress, `tshark` panel, and audit log before any compliance claim.
