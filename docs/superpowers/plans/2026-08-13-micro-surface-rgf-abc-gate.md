# Micro-Surface Rolling Guidance A/B/C Gate Implementation Plan

**Goal:** Determine whether scale-aware Rolling Guidance filtering can keep the coherent oval scar/meso relief in the base layer while retaining pore-scale residual detail.

**Evidence basis:** ECCV 2014 Rolling Guidance Filter separates structures by scale using Gaussian small-structure removal followed by iterative edge recovery. OpenCV ximgproc provides `rollingGuidanceFilter` directly.

## Variants
- A: existing Gaussian sigma 6 baseline.
- B: Rolling Guidance Filter, d=-1, sigmaColor=25, sigmaSpace=12, numOfIter=4.
- C: Rolling Guidance Filter, d=-1, sigmaColor=25, sigmaSpace=24, numOfIter=4.

## Locked invariants
- Branch `experiment/gnm-appearance-gate`; never `main`.
- Same 4096² DRL displacement proxy and exact PIL consumer channel domain.
- Same GNM v3 target, <=15 mm / <=60° correspondence contract, transfer size 1024.
- Bump distance 0.35 mm, strength 0.32.
- Same neutral albedo, camera, lights, render samples.
- Identity diffuse excluded; no raw or derived DRL maps uploaded.

## Hard gates
1. OpenCV ximgproc `rollingGuidanceFilter` must exist in the runner.
2. A/B/C low-pass files must round-trip through Pillow to the exact source consumer shape/domain.
3. `micro_height_from_lowpass(..., percentile=99.5)` preflight scale must exactly match renderer scale.
4. Correspondence and bump invariants must be identical across A/B/C.
5. Numeric GREEN is insufficient; GPT must inspect face-close and 3/4-close comparison renders.

## Decision
- `KEEP_RGF12` or `KEEP_RGF24` only if the oval scar is materially suppressed while pore/fine wrinkle detail remains useful.
- `KEEP_GAUSSIAN6` if RGF damages useful micro-detail without suppressing the scar.
- `NEED_SEMANTIC_OR_LOCAL_MASK_DECOMPOSITION` if valid RGF variants still retain the oval scar.
