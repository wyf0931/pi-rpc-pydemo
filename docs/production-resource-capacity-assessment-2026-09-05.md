# Production resource and concurrency assessment

Date: 2026-09-05 (Asia/Shanghai)

## Executive conclusion

The production host currently has 2 vCPU and 3.6 GiB RAM. A Pi RPC process
started with the real Agent extensions and skills configuration uses about
129 MiB RSS after startup. Measuring the container rather than summing RSS
(which counts shared pages more than once), the observed incremental cost was
about 80 MiB per additional loaded Pi process.

Use the following provisional operating limits until a prompt-generation load
test is available:

| Limit | Working chats |
| --- | ---: |
| Target | 12 |
| Memory/pressure warning | 16 |
| Protection ceiling | 20 |

These are capacity estimates, not a throughput or availability guarantee.

## Host snapshot

| Resource | Observation |
| --- | ---: |
| CPU | 2 vCPU |
| RAM | 3.6 GiB total, about 2.6 GiB available |
| Swap | 1.9 GiB total, 344 MiB used |
| Root disk | 59 GiB total, 37 GiB used (65%), 21 GiB available |
| Host load | 0.25 / 0.39 / 0.25 (1/5/15 minute) |

The OMA container has no CPU or memory cgroup limit and therefore competes
with the other containers and the host directly.

## Container and persistent-state baseline

At idle, `oma-studio` used about 55 MiB and 0.14% CPU. Other active containers
used about 45 MiB combined. The OMA image was about 909 MiB. Persistent OMA
state under `/opt/apps/oma-studio/shared` was about 186 MiB, mostly the Pi home
directory (about 182 MiB).

Docker reported 10.26 GiB of images and 12.65 GiB of build cache, of which
about 3.07 GiB was reclaimable. The root disk is not an immediate chat
capacity bottleneck, but build-cache retention should be monitored.

## Pi process experiment

The experiment ran one, then two additional Pi RPC processes in the production
container. Each process used the existing session's working-directory mapping,
the production provider/model, the Agent's extensions and skills, and the
normal tool allowlist. No model prompt was sent and no transcript content was
modified.

After startup stabilized, four samples with three Pi processes showed:

| Measure | Result |
| --- | ---: |
| Pi RSS total | 395,864–396,336 KiB |
| Pi RSS average | about 132,000 KiB (129 MiB) per process |
| OMA container memory | 294.6–295.1 MiB |
| OMA container idle baseline | about 55 MiB |
| Container incremental cost | about 80 MiB per Pi process |
| Stable CPU | below 1% for the three idle RPC processes |

One process briefly reached about 1.2 CPU cores during extension/skill
startup. Startup spikes therefore matter even though steady-state idle CPU is
low.

## Capacity calculation and caveats

Using the measured container increment, 2.6 GiB of currently available host
memory would imply roughly 32 additional processes mathematically. Keeping
approximately 0.8–1.0 GiB reserved for the OS, other containers, filesystem
cache, swap avoidance, and workload variance reduces the practical estimate to
about 20–24 processes. A lower operating target of 12–16 leaves room for long
transcripts, tool results, concurrent startup spikes, and temporary allocations.

The experiment measured loaded RPC processes without generation. Real prompts
can consume more memory as context, tool output, streaming buffers, and model
responses grow. CPU throughput, provider latency, and rate limits were not
measured. A staging or controlled production load test that sends representative
prompts is required before increasing the protection ceiling.

## Recommended monitoring

Track `docker stats` for OMA memory/CPU, active Pi process count, host
`MemAvailable`, swap usage, OOM events, Pi process exits, and per-chat startup
latency. Alert before the 16-chat warning threshold and reject or queue new
work near the 20-chat protection ceiling.
