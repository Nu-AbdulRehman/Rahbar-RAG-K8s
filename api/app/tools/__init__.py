"""Command-line tools over the trace records (RAGOps D2, D3). They run anywhere the api
package does: inside an api pod (`kubectl exec deploy/api -- python -m app.tools...`, the
trace volume is mounted there) or on a laptop from scripts/."""
