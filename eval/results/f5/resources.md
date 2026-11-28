# F5: requests and limits from measurements

Source: `kubectl top pods -n rahbar --containers` every 5 s from 10:46 to 11:12 UTC on
2026-11-28 (`kubectl-top-pods-containers.txt` here), on minikube (docker driver, 8 GB, 4
CPUs) with Ollama on the host GPU. The window covers three ingestion runs (the minilm and
k6 candidate collections, Batch B), four suite runs as Jobs (baseline twice, k6, minilm),
and a burst of 82 questions through the Ingress, 6 at a time (107.9 s, all 200, p50
9.05 s). metrics-server samples every 15 s, so a peak shorter than that can be missed;
every limit keeps headroom for it.

| workload | peak CPU | peak memory | when | requests | limits | change |
| --- | --- | --- | --- | --- | --- | --- |
| api (each of 3) | 87m | 74Mi | eval and burst | 100m / 160Mi | 500m / 320Mi | none: A02 measured 186m at start-up (docs/evidence/kubectl-top.txt); memory 2x the new peak |
| api-candidate | 96m | 72Mi | suite runs | 100m / 160Mi | 500m / 320Mi | same image and load shape as the api |
| chroma | 16m | 156Mi | after 4 collections (rahbar, -k6, -minilm, Batch B) | 50m / **192Mi** | 500m / 512Mi | request raised from 160Mi: the A02 peak was 107Mi with one collection, now 156Mi with four |
| indexer Job / CronJob / candidate index Jobs | 1381m | 1073Mi | candidate build, Batch B | 500m / 1280Mi | 2 / 1792Mi | none: A02's OCR peak 1159Mi still the larger one; limit 1.5x it (exit 137 at 768Mi, failure-log) |
| suite (eval image, Member 1's eval Job) | 91m | 93Mi | baseline, two runs | recommended 100m / 128Mi | 500m / 256Mi | for k8s/eval-job.yaml |
| gate Job | 0.1 s CPU | 18 MiB peak RSS | `resource.getrusage` in the eval image | 50m / 64Mi | 250m / 128Mi | new: finishes before metrics-server samples it |
| redis | 4m | 15Mi | idle | unchanged (A02) | unchanged | |
| ui | 1m | 2Mi | all | unchanged (A02) | unchanged | |
| ragops-shell | 11m | under 1Mi | kubectl cp | 10m / 32Mi | 250m / 256Mi | tool pod; limit covers pipeline.ops status |

Ollama runs on the host, outside the cluster, so its GPU and memory are not in these
numbers; the api's and the suite's time is mostly spent waiting on it.
