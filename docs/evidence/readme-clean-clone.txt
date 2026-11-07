# README "Run it on minikube, from a clean clone", run on 2026-11-07 on a brand-new minikube (Windows, Docker Desktop)
# Script: the README steps in order; `make` targets replaced by the Makefile's own commands, because Git Bash has no make.
# Result: works end to end, 763 s from minikube delete to a cited answer and a correct decline.
# One finding, fixed in the same PR: every api pod was killed once by its startup probe while Chroma had no endpoints (see the end).

## 17:04:55 0. fresh minikube: minikube delete
💀  Removed all traces of the "minikube" cluster.

## 17:04:56 clone: git clone -b fix/s4.2-indexer-retries https://github.com/Nu-AbdulRehman/Rahbar-RAG-K8s.git
d2f304b fix(k8s): indexer Job and CronJob retry 6 times, not 2 (§4.2)

## 17:04:59 1. make cluster MINIKUBE_MEMORY=5120
🌟  Enabled addons: storage-provisioner, default-storageclass
🏄  Done! kubectl is now configured to use "minikube" cluster and "default" namespace by default
🌟  The 'metrics-server' addon is enabled
🌟  The 'ingress' addon is enabled

## 17:09:51 2. minikube ssh "grep host.minikube.internal /etc/hosts"
192.168.65.254	host.minikube.internal
ipBlocks in networkpolicy.yaml matching: 2

## 17:09:52 3. make images
sha256:7333094148d3203f40dc7ccf569fa902df7d6856695f177a50468ab71023e3ac
sha256:1d339c5c0fe3b7de8a74990af296b8bc0d9088166c42f4fee60c083ac78cdf25
sha256:603872a03566a979132d4ba6c426a0cb925e715077ae78d50be3f4c9ba4ed19b
docker.io/library/rahbar-ui:dev
docker.io/library/rahbar-indexer:dev
docker.io/library/rahbar-api:dev

## 17:11:32 4. kubectl apply -k k8s/overlays/dev
namespace/rahbar created
serviceaccount/api created
serviceaccount/chroma created
serviceaccount/indexer created
serviceaccount/redis created
serviceaccount/ui created
configmap/rahbar-config created
service/api created
service/chroma created
service/redis created
service/ui created
persistentvolumeclaim/redis-data created
deployment.apps/api created
deployment.apps/redis created
deployment.apps/ui created
statefulset.apps/chroma created
cronjob.batch/reindex created
horizontalpodautoscaler.autoscaling/api created
job.batch/indexer created
ingress.networking.k8s.io/rahbar created
networkpolicy.networking.k8s.io/allow-dns created
networkpolicy.networking.k8s.io/api created
networkpolicy.networking.k8s.io/chroma created
networkpolicy.networking.k8s.io/default-deny created
networkpolicy.networking.k8s.io/indexer created
networkpolicy.networking.k8s.io/redis created
networkpolicy.networking.k8s.io/ui created

## 17:11:35 5. make secret: skipped (LLM_PROVIDER=ollama-host needs no key)

## 17:11:35 6. kubectl -n rahbar wait --for=condition=complete job/indexer --timeout=20m
job.batch/indexer condition met
NAME            READY   STATUS      RESTARTS   AGE
indexer-7sth8   0/1     Completed   0          5m51s
9 of 9 match the manifest
{"ts": "2026-11-07T17:17:21Z", "logger": "rahbar.indexer", "msg": "indexer finished", "chunks": 803, "cache_generation": 1, "seconds": 267.0}

## 17:17:25 6. kubectl -n rahbar rollout status deploy/api
Waiting for deployment "api" rollout to finish: 0 of 3 updated replicas are available...
Waiting for deployment "api" rollout to finish: 1 of 3 updated replicas are available...
Waiting for deployment "api" rollout to finish: 2 of 3 updated replicas are available...
deployment "api" successfully rolled out
NAME                         READY   STATUS      RESTARTS        AGE
pod/api-859cfbcb8b-9cddf     1/1     Running     1 (4m35s ago)   5m55s
pod/api-859cfbcb8b-lsdwr     1/1     Running     1 (4m35s ago)   5m55s
pod/api-859cfbcb8b-q96cz     1/1     Running     1 (4m35s ago)   5m55s
pod/chroma-0                 1/1     Running     0               5m55s
pod/indexer-7sth8            0/1     Completed   0               5m55s
pod/redis-6ff6f96dc4-mtfvv   1/1     Running     0               5m55s
pod/ui-56df4cc69d-j2n8l      1/1     Running     0               5m55s

NAME             TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)    AGE
service/api      ClusterIP   10.101.229.149   <none>        8000/TCP   5m56s
service/chroma   ClusterIP   10.97.165.34     <none>        8000/TCP   5m55s
service/redis    ClusterIP   10.100.81.132    <none>        6379/TCP   5m55s
service/ui       ClusterIP   10.99.198.130    <none>        8080/TCP   5m55s

NAME                               CLASS   HOSTS          ADDRESS        PORTS   AGE
ingress.networking.k8s.io/rahbar   nginx   rahbar.local   192.168.49.2   80      5m55s

NAME                                      REFERENCE        TARGETS              MINPODS   MAXPODS   REPLICAS   AGE
horizontalpodautoscaler.autoscaling/api   Deployment/api   cpu: <unknown>/70%   3         8         3          5m55s

## 17:17:29 7. ask through the Ingress (kubectl port-forward to the ingress controller stands in for minikube tunnel, which needs an elevated terminal on Windows)
$ make ask INGRESS_IP=127.0.0.1 Q="What CGPA puts a student on academic warning?"
{
    "request_id": "38b17cb5d599c6bdc053e8a764758693",
    "answer": "2.00 [academic-rules-handbook-jun-2026.pdf / Academic Warning/Probation]",
    "citations": [
        {
            "source": "academic-rules-handbook-jun-2026.pdf",
            "section": "Academic Warning/Probation",
            "page": 24
        }
    ],
    "answered_from_context": true,
    "confidence": "high",
    "retrieved": [
        {
            "chunk_id": "academic-rules-handbook-jun-2026.pdf#0039",
            "source": "academic-rules-handbook-jun-2026.pdf",
            "section": "Academic Warning/Probation",
            "page": 24,
            "score": 0.8557
        },
$ make ask Q="What time is the hostel curfew?"   (must decline)
answered_from_context: False | The documents I can search do not cover this question, so I cannot answer it from them. Please check with the relevant office.

total: 763 s from minikube delete to the first answer

## Finding: api RESTARTS 1 on all three pods
kubectl describe: "Startup probe failed: ... connection refused" (x25), then "Container api failed startup probe, will be restarted".
The log shows the lifespan waiting from container start until 17:12:53 for the startup pin check's Chroma connect: the chroma Service had no endpoints while its image was pulled.

## After the fix (startup pin check in a thread), same condition reproduced: chroma scaled to 0, api restarted
t+100 s: new pod api-67c987f66-t96jt  0/1  Running  RESTARTS 0   (alive, not ready: correct)
chroma scaled back to 1: deployment "api" successfully rolled out, all new pods 1/1, RESTARTS 0

## HPA after metrics-server warmed up (7 min): api   Deployment/api   cpu: 4%/70%   3   8   3
