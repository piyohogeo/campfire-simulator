# Phase 6FH — readback-free lifecycle qualification

Phase 6FH separates the low-frequency native stage-close failure captured by Phase 6FG from NanoVDB memory and alias evidence. Phase 6FG remains a frozen safe stop: five balanced A/B/C conditions passed, sequence 2 A timed out, and the nine-process population is not qualified or reclassified.

## Read-only Phase 6FG audit

The failed condition was a no-readback A control. Its durable sequence was:

- timeline stop requested at `02:30:54.993239Z` and confirmed at `02:30:55.051379Z`;
- eight renderer updates completed at `02:30:55.459301Z`;
- Flow interface and Emitter references were absent by `02:30:55.480322Z`;
- volume/provider/readback/collector references were absent by `02:30:55.502924Z`;
- `close_stage_async()` began at `02:30:55.513431Z` and timed out after the frozen 180-second bound at `02:33:55.504798Z`;
- the stage was no longer present at the timeout marker, but the await did not return and `stage_closed` remained false;
- the diagnostic extension callback began at `02:34:23.7351745Z` and ended at `02:34:23.7401752Z`;
- Kit continued native extension/plugin shutdown. The final Kit log entered `omni.usd-1.16.0` shutdown, released Hydra engine 1024, and then reported its own hang detector at `02:36:24Z`;
- the outer 600-second guard reached the residual diagnostic boundary at about `02:39:14Z`.

Bounded CDB verified the target PID, creation time, and executable path, attached non-invasively, and captured a complete module list. The first captured native thread passed through `omni_usd!UsdManager::destroyContext+0x160`, `_usd`, Python, `carb_scripting_python_plugin`, `omni_ext_plugin!carbOnPluginShutdown`, and `omni_kit_app_plugin`. A second profiler thread was sleeping in `ntdll!NtDelayExecution`; the log only reached the header for thread 2 before the 45-second helper timeout. Consequently the old `THREAD_STACKS` marker means stack enumeration started, not that all 145 threads were captured. No lock owner, GPU fence wait, renderer wait, or Python callback owner was established. None of the five accepted NGX telemetry tokens appeared, so this is not the known NGX signature.

CDB itself was killed by its helper timeout and was absent; Kit Private Bytes stayed at 10,138,525,696 bytes and accumulated only 0.328125 CPU seconds during that diagnostic interval. This is consistent with a low-CPU native wait but is not enough to identify its wait object or owner. The outer guard later removed only the descendants it had recorded by PID plus creation time: Kit 48372, its conhost 34360, and telemetry transmitter 21932. All were confirmed absent. No full dump was created because the lightweight diagnostic explicitly recorded `dump_required=false`; no automatic dump or upload fallback exists.

Confirmed facts above are distinguished from these hypotheses: an SRW lock, renderer/GPU fence, USD loader lock, or Python callback dependency remains possible, but the incomplete thread population does not select among them. The `omni_usd`/extension-shutdown boundary is narrower than a generic shutdown residual, yet private NVIDIA/Omniverse symbols or a bounded one-time full dump would be required to identify an owner if the improved stack path still cannot do so.

## Frozen runtime contract

The machine-readable contract is `scripts/phase6fh_lifecycle_qualification_contract.json`. Its SHA-256 is recorded beside it. The population is six independent no-readback A controls. All use the Phase 6FG four-log fixture, startup, 24-second running-Flow observation, timeline stop, eight pre-close renderer updates, reference-release order, 180-second stage-close bound, and existing absolute resource ceilings.

Execution stops after all six normal exits or the first lifecycle failure. A failure is not retried. One same-boundary hang is sufficient to stop when public evidence cannot extend beyond `omni_usd` or extension shutdown internals. This is an incidence/boundary qualification, not a promise to solve the native root cause.

## Bounded debugger contract

The old single 45-second CDB command mixed symbol loading, modules, 145 all-thread stacks, and detach. Phase 6FH separates it into cache-only non-invasive passes:

- attach plus module inventory: at most 30 seconds;
- all-thread stacks, depth 16: at most 45 seconds;
- detach-recovery attach, only if the stack pass did not reach `qd`: at most 30 seconds.

Each pass writes stdout/stderr directly to capped files, runs below the 512 MiB diagnostic limit, uses the existing atomic capture lock, verifies exact target identity, and persists markers. The worst-case debugger envelope is 105 seconds. Missing private symbols retain raw module+offset evidence and remain fail-closed. No system debugger registration, WER change, automatic full dump, or automatic upload is allowed. The Phase 6EL fixture covers normal attach/detach, locked log, target exit, forced timeout, and abnormal CDB exit before Kit qualification begins.

## Operation and lifecycle axes

Future paired evidence must report two independent axes. The operation axis covers exact A/B/C markers, resource ceilings, call counts, alias identity, settling, and paired order. The lifecycle axis covers stage close, extension shutdown, normal OS exit, residual processes, and any timeout/CDB/forced cleanup. Operation evidence may remain useful when lifecycle fails after the operation completed, but overall production qualification requires both axes. A lifecycle failure is never relabeled as a memory pass or a normal exit.

Phase 6FG is not restarted by this phase. After Phase 6FH, a new explicit approval is required. If all six controls exit normally, the result is bounded non-reproduction and detailed markers remain armed. If the same native boundary recurs without new public evidence, it becomes a monitored known lifecycle issue rather than an indefinitely repeated investigation. If a self-owned ordering difference appears, it must be tested later as a one-variable probe before any paired-harness change.

## Runtime result: prerequisite safe stop

The frozen population stopped after run01. Its per-frame startup samples were fresh and remained at exactly 24 active blocks from frame 1 through frame 120. Timeline time and Kit update index advanced; the Point contract remained 1,440 total, 1,344 active, revision 1, with the expected fuel, temperature, and smoke totals. Stage, payload, Flow-interface, and Emitter identities remained stable. The fixed four-log fixture nevertheless failed its predeclared representative threshold of 128 blocks, so this is `small_field_ingestion`, not a valid lifecycle-control sample.

No readback or NumPy conversion occurred. Timeline stop took 0.056063 seconds, eight renderer drains 0.415005 seconds, reference release 0.031546 seconds, `close_stage_async()` 3.002983 seconds, and the extension shutdown callback 0.002500 seconds. The Kit process disappeared without outer forced cleanup, but the prerequisite failure produced exit code 1; it is therefore not a normal OS exit. Fatal, dump, automatic upload, device lost, TDR, and cleanup residual counts were zero. CDB was not invoked.

The formal result is `prerequisite_safe_stop`: 1 of 6 launch slots was attempted, 0 representative lifecycle controls completed, and the remaining five were not started. The Phase 6FG stage-close failure did not reproduce in this non-representative sample, but the native lifecycle failure incidence is not measurable from it. This result neither resolves nor strengthens any particular lock-owner hypothesis.

## Restart and replacement proposal

Phase 6FG remains frozen and is not restarted. A future explicitly approved lifecycle contract may predeclare at most two extra launch slots for startup-prerequisite failures. Such a launch is preserved in startup-monitoring evidence and is not called a retry or a lifecycle pass. An operation failure or native lifecycle failure is never replaced and stops the population immediately. A later paired A/B/C contract may use the same distinction, but overall single-readback qualification still requires both operation and lifecycle axes to pass.

No full dump is proposed from the current evidence. A bounded one-time dump remains an approval-only option if a representative control reproduces the same `omni_usd` boundary and the staged cache-only CDB path cannot extend the public module+offset evidence.
