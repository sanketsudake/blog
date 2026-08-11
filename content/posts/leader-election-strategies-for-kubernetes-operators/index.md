+++
title = "Leader Election Strategies for Scaling Kubernetes Operators"
date = 2026-04-25T10:00:00+05:30
tags = ["kubernetes", "operators", "leader-election", "controller-runtime", "go"]
categories = []
summary = "Why scaling Kubernetes operators needs coordination between replicas — and three lease-based leader-election strategies that fix what horizontal scale breaks."
showTableOfContents = true
+++

A [Kubernetes operator](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/) is a controller that watches a Custom Resource and reconciles desired state in a loop.
Most operators ship as a single Deployment replica; fine until reconciliation latency, throughput, or a node failure forces the question of how to run more than one.

Operators are easy to deploy as one replica and surprisingly hard to scale safely.
The moment you go from a single replica to many, you have introduced a coordination problem that the controller pattern does not solve for you.
The instinctive `kubectl scale --replicas=3` will often make things worse before it makes them better.

This post is a tour of the three coordination strategies we built around the Kubernetes Lease for operators: when each one applies, how they sit on top of the same Kubernetes primitive, and how to see them in action on a Kubernetes cluster.

We will start with the failure modes that scaling forces you to think about, look at why a single shared primitive (the Kubernetes Lease) is enough to express three very different coordination patterns, and finish with a hands-on walkthrough.

## When one operator replica falls short

Picture an operator that reconciles a few hundred CRs by calling a slow external API.
One replica works fine in dev.
In production, reconciliations back up, the queue grows, and the latency SLO slips.
The instinctive fix, `kubectl scale --replicas=3`, makes things dramatically worse: now three replicas race on the same CRs, fight over Status updates, and triple the load on the external API.

{{< mermaid >}}
flowchart LR
    CR[(CustomResource)]
    P1[Pod 1] -->|reconcile| CR
    P2[Pod 2] -->|reconcile| CR
    P3[Pod 3] -->|reconcile| CR
    CR -.->|conflicting<br/>Status updates| API[kube-apiserver]
    P1 -.->|duplicate<br/>external calls| EXT[External API]
    P2 -.->|duplicate<br/>external calls| EXT
    P3 -.->|duplicate<br/>external calls| EXT
    classDef pod fill:#fb7185,stroke:#be123c,color:#fff
    classDef resource fill:#f59e0b,stroke:#b45309,color:#fff
    classDef external fill:#64748b,stroke:#334155,color:#fff
    class P1,P2,P3 pod
    class CR resource
    class API,EXT external
{{< /mermaid >}}

There are three distinct *forces* that push us toward running more than one replica, and each one needs a different coordination answer.

1. **Availability.**
   The operator must survive a node or pod failure without a human paging in.
   This is a *failover* problem.
2. **Throughput.**
   When reconciliation is CPU-bound or external-API-bound, a single active replica is a bottleneck.
   We need to distribute *work* across replicas, not just stand more of them by.
3. **Stable identity.**
   Some workloads need a deterministic owner per shard or per ordinal so on-disk state, external state, or peer membership remains consistent across restarts.

Each strategy in this post solves one of these forces.
The trick is knowing which.

## Kubernetes' built-in leader election

Before we get to strategies, here is the primitive every one of them rests on.

Kubernetes ships with a coordination atom called a [`Lease`](https://kubernetes.io/docs/concepts/architecture/leases/).
Think of a Lease as a sticky note in `etcd` that says *"I, pod X, am the current owner of this name; I'll prove I'm still alive by re-stamping this note every few seconds."*
If pod X stops re-stamping (it crashed, the node died, the network split), the sticky note expires after a short window and any other pod is free to claim it.

That's the whole mechanism.
There is no separate election service, no Raft, no ZooKeeper.
Every pod that wants to participate writes to the same Lease object, and the API server's optimistic concurrency control guarantees that only one writer wins at a time.
Most operator frameworks (the common one being [`controller-runtime`](https://pkg.go.dev/sigs.k8s.io/controller-runtime)) wrap this for you, so you usually never write the renew/acquire loop by hand.

What you *do* tune are the timing windows.
The settings shared by every strategy in this post:

```text
LeaseDuration   = 15s   # how long the holder is owner without a renewal
RenewDeadline   = 10s   # how long the holder retries renew before giving up
RetryPeriod     = 2s    # how often non-holders try to acquire
ReleaseOnCancel = true  # release the lease cleanly on shutdown
```

The 15-second `LeaseDuration` is your worst-case failover budget.
If the current holder's pod dies, a competitor will pick the Lease up within roughly that window.
The exact values live in [`elector.go`](https://github.com/sanketsudake/k8s-operator-leader-election/blob/master/elector.go).

## Three ways to compose the same primitive

A Lease on its own only answers one question: *who is the current owner of this name?*
Different leader-election strategies are different answers to the question *what does "ownership" mean for the work this operator does?*

Three meaningful answers map cleanly onto the three forces from the previous section.

- **One Lease, one leader.**
  All pods race for a single Lease.
  Whoever wins runs everything; the rest stand by, ready to take over the moment the lease expires.
  Ownership means *"I am the active replica."*
  This is failover.
- **N Leases, distribution emerges.**
  Instead of one Lease, run *N* of them, and route each piece of work to a Lease via a hash.
  Every pod independently competes for every Lease, so multiple pods end up doing real work in parallel, each owning a slice of the keyspace.
  There is no central rebalancer; distribution is whatever the N independent races settle into.
  This is throughput.
- **One Lease, one stable name.**
  Same single-Lease shape as the first answer, but each pod is also given a stable identity by the platform: a StatefulSet ordinal, a stable hostname, a stable PVC.
  Ownership now means *"the right named pod is currently active,"* which matters when on-disk or peer state has to follow a particular replica across restarts.
  This is identity.

The rest of the post walks through them in turn.

## Strategy 1: Active-Passive (the baseline)

This is the simplest pattern, and the one `controller-runtime` gives you for free.
Every pod competes for a single shared Lease.
Whoever wins becomes the leader and runs the reconcile loop; the rest stand by, ready to take over when the lease expires.

{{< mermaid >}}
flowchart TD
    A[Pod starts] --> B[Compete for single Lease]
    B -->|won| C[Leader: process all objects]
    B -->|lost| D[Standby: wait for lease expiry]
    D -->|lease expired| B
    classDef process fill:#38bdf8,stroke:#0369a1,color:#fff
    classDef lease fill:#f59e0b,stroke:#b45309,color:#fff
    classDef leader fill:#10b981,stroke:#047857,color:#fff
    classDef standby fill:#94a3b8,stroke:#475569,color:#fff
    class A process
    class B lease
    class C leader
    class D standby
{{< /mermaid >}}

There is nothing per-object to configure here.
The question "am I the leader?" has the same answer for every reconcile: yes if this pod holds the Lease, no otherwise.
When the leader pod dies, its Lease lapses; within roughly the `LeaseDuration` window, a standby wins it and starts reconciling.

**When to use Active-Passive:** you only need failover.
Reconciliation is comfortably handled by one replica, and the standby pods exist to take over on failure, not to share the load.

## Strategy 2: Dynamic Sharding (when one leader can't keep up)

Active-Passive caps your throughput at one replica's worth of work.
The moment your reconcile latency or external-API call rate becomes the bottleneck, more replicas have to *do work in parallel* rather than just stand by.

The pattern: instead of one shared Lease, we run **N bucket leases** named `<prefix>-0` … `<prefix>-(N-1)`.
Every pod independently competes for *all N* of them.
A pod becomes the leader for bucket `B` when it wins lease `<prefix>-B`.
`IsLeader(key)` does a fast hash (`fnv32a(key) % N`) and returns whether *this pod* owns the lease for that bucket.

{{< mermaid >}}
flowchart TD
    A[Pod starts] --> B["Start N lease electors (one per bucket)"]
    B --> C["Compete for lease prefix-0 … prefix-(N-1)"]
    C --> D[Won some bucket leases]
    C --> E[Lost some bucket leases]
    D --> F["IsLeader(key): hash(key)%N → owned bucket → true"]
    E --> G["IsLeader(key): hash(key)%N → unowned bucket → false"]
    classDef process fill:#38bdf8,stroke:#0369a1,color:#fff
    classDef lease fill:#f59e0b,stroke:#b45309,color:#fff
    classDef leader fill:#10b981,stroke:#047857,color:#fff
    classDef standby fill:#94a3b8,stroke:#475569,color:#fff
    class A,B process
    class C lease
    class D,F leader
    class E,G standby
{{< /mermaid >}}

### How distribution emerges

Here is the part that took the longest to convince ourselves was right:

> **There is no rebalancer.**
> Distribution is an emergent property of N independent leader elections.

No central coordinator decides "Pod A owns bucket 0, Pod B owns bucket 1."
Each pod runs N independent `leaseElector` goroutines in parallel and competes for every bucket.
Whoever wins, wins.
The distribution that falls out of this is a function of how many pods (`M`) are competing for how many buckets (`N`):

| Scenario | Behavior |
|----------|----------|
| **M = N** | Steady state. Each pod wins ~1 bucket. |
| **M < N** | Some pods hold multiple buckets. With 3 pods and 4 buckets, expect ~2 buckets each (depending on the lease race). |
| **M > N** | At most N pods are active leaders; extras sit as hot-standby per bucket. |

{{< mermaid >}}
flowchart LR
    subgraph "M=3 pods, N=4 buckets (M < N)"
        P1[Pod A] -->|leads| B0[Bucket 0]
        P1 -->|leads| B1[Bucket 1]
        P2[Pod B] -->|leads| B2[Bucket 2]
        P3[Pod C] -->|leads| B3[Bucket 3]
    end
    classDef leader fill:#10b981,stroke:#047857,color:#fff
    classDef lease fill:#f59e0b,stroke:#b45309,color:#fff
    class P1,P2,P3 leader
    class B0,B1,B2,B3 lease
{{< /mermaid >}}

{{< mermaid >}}
flowchart LR
    subgraph "M=4 pods, N=2 buckets (M > N)"
        P1[Pod A] -->|leads| B0[Bucket 0]
        P2[Pod B] -->|leads| B1[Bucket 1]
        P3[Pod C] -.->|standby| B0
        P4[Pod D] -.->|standby| B1
    end
    classDef leader fill:#10b981,stroke:#047857,color:#fff
    classDef standby fill:#94a3b8,stroke:#475569,color:#fff
    classDef lease fill:#f59e0b,stroke:#b45309,color:#fff
    class P1,P2 leader
    class P3,P4 standby
    class B0,B1 lease
{{< /mermaid >}}

The reason we deliberately *avoided* a rebalancer is that any external "scheduler" service that decides "Pod X gets bucket Y" becomes a new SPOF, the very problem leader election is supposed to solve.
Letting bucket ownership emerge from N independent races means failover is also emergent: when a bucket-owning pod dies, its lease expires after ~15s and a surviving competitor wins it on the next retry, with no external trigger.

The sharded elector also lets a pod ask the inverse question: not "do I own this key?" but "which buckets do I currently hold?"
That's useful when the operator does background work (logging, metrics, or any periodic sweep) that iterates over owned shards rather than reacting to incoming keys.

The most fun way to see this is to scale the deployment up and down on Kind:

```bash
make kind-deploy-sharded
# Default: 3 pods, 4 buckets, M < N, some pods hold two buckets each.
kubectl logs -l strategy=sharded -f

# Watch buckets redistribute as we scale to M = N
kubectl scale deploy leader-demo-sharded --replicas=4

# M > N, extras become hot-standby
kubectl scale deploy leader-demo-sharded --replicas=6

# Scale down, surviving pods automatically pick up orphaned buckets
kubectl scale deploy leader-demo-sharded --replicas=2
```

In the logs from each pod, watch the `ownedBuckets` list shift around as leases get released and re-won.
There is no external event triggering this.
Only the lease expiry and renew loop running everywhere, all the time.

**When to use Dynamic Sharding:** you need throughput.
The reconcile work itself has to be split across replicas.
Pick `N` based on how much parallelism you expect, not how many pods you currently run; the M-vs-N table above tells you how the system behaves in any configuration.

## Strategy 3: StatefulSet identity (when ordinals matter)

Sharding handles "split work across replicas."
But sometimes the *identity* of a replica matters too.
If your shard-0 has on-disk state (a local index, a cache, a peer membership token), it has to be the same logical pod across restarts, with the same hostname, the same PVC, the same place in a cluster topology.

A Lease can decide *who is currently active*.
A StatefulSet decides *what identity* a pod has.
The third strategy combines both.

{{< mermaid >}}
flowchart TD
    A[Pod starts] --> B["Resolve identity (arg or HOSTNAME)"]
    B --> C[Compete for shared Lease]
    C -->|won| D[Leader: active instance]
    C -->|lost| E[Standby: wait for lease expiry]
    E -->|lease expired| C
    classDef process fill:#38bdf8,stroke:#0369a1,color:#fff
    classDef lease fill:#f59e0b,stroke:#b45309,color:#fff
    classDef leader fill:#10b981,stroke:#047857,color:#fff
    classDef standby fill:#94a3b8,stroke:#475569,color:#fff
    class A,B process
    class C lease
    class D leader
    class E standby
{{< /mermaid >}}

Mechanically this looks identical to Active-Passive: one shared Lease, one active leader, others on standby.
The difference is in *who* the leader claims to be.
Under a StatefulSet, every pod's hostname is its ordinal name (`leader-demo-statefulset-0`, `-1`, …), and that name is stable across restarts and rescheduling, with a matching stable PVC attached.
The elector uses that hostname as its lease identity, so the Lease records *which named pod* is currently active, not just which ephemeral instance.

If the leader pod dies, the StatefulSet recreates a pod with the *same* name; once the Lease expires, that pod is again the natural candidate to take leadership, with its on-disk state, its peer membership, and its place in the topology intact.

**When to use StatefulSet identity:** you need stable identity.
Your workload's correctness depends on a particular replica being recoverable as itself, not just on *some* replica being active.

## Hands-on: a brief Kind walkthrough

The full Makefile has individual targets for each strategy, but the four-step path covers everything:

```bash
# 1. Spin up a Kind cluster
make kind-create

# 2. Build the demo image and load it into Kind
make kind-load

# 3. Deploy all three strategies side-by-side
make kind-deploy-all

# 4. Tail logs across every strategy's pods
make kind-logs
```

The most rewarding thing to do once it is running is to scale the sharded deployment up and down (`kubectl scale deploy leader-demo-sharded --replicas=N`) and watch `ownedBuckets` rearrange in the logs of each surviving pod.
That is the no-rebalancer behavior we described above, in real time.

If you want to dig into the invariants in code, look at [`elector_test.go`](https://github.com/sanketsudake/k8s-operator-leader-election/blob/master/elector_test.go).
You can run the tests against a real `kube-apiserver` + `etcd` via `controller-runtime`'s `envtest` (not a fake clientset).

To clean everything up:

```bash
make kind-cleanup
```

## Picking a strategy

Three strategies, three forces.
Here is the condensed decision matrix:

| If you need… | Use | Lease count | Notes |
|---|---|---|---|
| Failover only | Active-Passive | 1 | Same as `controller-runtime`'s built-in option. |
| Parallelism across many CRs | Dynamic Sharding | N | No rebalancer; reconcile work is distributed by hash. |
| Stable per-replica identity | StatefulSet | 1 | Pair with a StatefulSet for ordinal hostnames + stable PVCs. |

A few trade-offs worth keeping in mind:

- More leases mean more API objects to renew and more log noise to watch, but no central coordinator means no SPOF added on top of the API server.
- Sharding pushes complexity into the *consumer* of `IsLeader(key)`.
  Every reconcile has to ask "do I own this key?" before doing work; getting that gate wrong undoes the whole point.
- StatefulSet identity adds operational weight (PVCs, ordered start, ordered shutdown).
  Use it when you actually need ordinal identity, not as a default.

## Summary

Scaling a Kubernetes operator is a coordination problem first and a performance problem second.
Once you have decided to run more than one replica, you have to answer three independent questions: how do replicas fail over, how do they share work, and how do they identify themselves to the outside world?

The Kubernetes Lease is the single primitive that makes all three answerable in clean Go code.
The three strategies in [`k8s-operator-leader-election`](https://github.com/sanketsudake/k8s-operator-leader-election) are essentially three different ways of composing leases: one lease for failover, N leases for sharding, one lease plus a StatefulSet for stable identity.
The non-obvious part is that sharding works *without* a rebalancer.
The M-vs-N distribution is whatever falls out of N independent leader races, and that is exactly what makes it robust.

If you want to read the full code, run the demo, or extend it with a new strategy of your own, the project is at [`github.com/sanketsudake/k8s-operator-leader-election`](https://github.com/sanketsudake/k8s-operator-leader-election).
Tests, deploy manifests, and a Kind-ready Makefile are all there.

If this scratched an itch, controllers and leader election get the full-book treatment in my free [Kubernetes Internals Worksheet](/books/k8s-worksheet/) — the reconcile machinery, the handover flow, and where both break in production.

We'd love to hear your thoughts on this post.
Start a conversation on [LinkedIn](https://www.linkedin.com/in/sanketsudake/).
