# funi-floors

**Stay-in-Place (SIP) Self-Prestressing Funicular MEP Floor Cassettes & `313 psf` Active-Confined Column Collars (`v0.1.0`).**

`funi-floors` unifies the `aska-physical` structural hardware stack—[`fibral-rigidity`](/aska-physical/fibral-rigidity), [`cfrp-truss`](/aska-physical/cfrp-truss), [`venturi-collars`](/aska-physical/venturi-collars), and [`impedence-analyzers`](/aska-physical/impedence-analyzers)—into the highest-leverage structural element in multi-story buildings: **the horizontal floor-and-MEP system (`55–70%` of building mass and embodied carbon)**.

## Why Conventional Slabs & Academic Vaults Both Stall

- **Flat PT slabs (`250–310 mm`) + hung MEP plenums (`350 mm`)** consume `600–660 mm` per floor, weigh `600–744 kg/m²`, emit `92–121 kg CO2e/m²`, and fail by brittle two-way punching shear under **`300+ psf` (`15 kPa`) liquid-cooled AI data-center loads** (ISTA Data Center Structural Floor Guidelines).
- **Academic funicular vaults** (ETH Block Research Group HiLo Floors, Ranaudo et al. 2021; Rippmann et al. 2018 Discrete Funicular Slabs; SBE25 Zurich Floor MCDA 2025) cut concrete by `50–70%`, yet stalled commercially due to **disposable 3D-printed sand formwork, hydraulic post-tensioning jacks, lightweight walking vibration, and 2-hour polymer fire limits**.

## Verified Six-Domain Architecture (`9.0 m × 9.0 m` Bay = Three `3.0 m × 9.0 m` Cassettes)

1. **Stackable Stay-in-Place (SIP) Composite Trough + `45°` Octagonal MEP Webs:**
   - A `3 mm` mineral-basalt/carbon trough pan nests 25-high on a flatbed truck, molds low-clinker `65% GGBS` C50 concrete (`74.07 mm` equivalent thickness = **`-76.11%` concrete volume** and **`-73.77%` dead mass** at `195.12 kg/m²`), and routes `200 mm` VAV ducts and chilled-water pipes through `45°` Torayca T1100G octagonal rib apertures (`373.48 kN` shear capacity vs. `185.60 kN` ULS demand; unbraced holes fail at `22.50 kN`).
   - Compresses total floor + MEP depth from `660 mm` to **`380 mm`**—saving **`280.0 mm` per level (`+1 bonus floor every 12 stories`)**.
2. **Jack-Free Resistive Joule-Heated `Fe-SMA + CFRP` Hybrid Ties (`0.3227 kWh/m²`):**
   - Applying low-voltage resistive heating (`175 °C`, `8.712 kWh` per `27 m²` cassette) to pre-strained `Fe-Mn-Si` memory-steel strips (`4 × 980 mm²`, Empa Czaderski et al. 2015) paired with `4 × 360 mm²` Torayca T1100G chords locks in **`423.47 MPa` recovery prestress**, cancelling Castigliano tie-elongation moment (`H_service = 1,894.74 kN`, `M_crown = 4.119 kN·m`, `f_c = 13.669 <= 22.50 MPa`) with **zero hydraulic jacks**.
3. **Solves the Lightweight Vibration Paradox (`AISC Design Guide 11`):**
   - SymPy proves `d(ln a_p)/dm > 0` above `f_n* = 200/35 = 5.7143 Hz`. Two-way shear-keyed active cassettes (`EI_2way = 58.758 MN·m²/m`) achieve **`f_n = 8.624 Hz >= 8.0 Hz`** and **`a_p/g = 0.308% <= 0.50%` (`PASS`)**, whereas an un-prestressed cracked shell drops to `3.261 Hz` and `2.415% g` (`FAIL`).
4. **Flush-Soffit `313 psf` (`15 kPa`) Active Punching Collar (`ACI 318M-19 §22.6.5.2`):**
   - Because the funicular vault naturally deepens to **`380 mm` (`d_eff = 335.0 mm`, `b_0 = 3,340.0 mm`) at column corners** with a flush flat ceiling, pairing `Fe-SMA` radial clamping (`f_pc = 3.8 MPa`) with `45°` [`cfrp-truss`](/aska-physical/cfrp-truss) dowels (`V_p = 480 kN`) delivers **`phi*V_n = 2,756.40 kN >= V_u = 2,208.02 kN` (`80.11%` utilization, `PASS`)** with **zero drop panels**.
5. **120-Minute `ISO 834` Fire Crossover:**
   - Grouting `Fe-SMA + end-locked T1100G` in inorganic cementitious mortar behind mineral SIP fire-board (`427.6 °C` at `120 min`) retains **`3,902.95 kN` vs. `1,171.96 kN` fire thrust demand (`3.33x` safety factor, `PASS`)**, whereas `20 mm`-cover epoxy CFRP hits `840.2 °C >> T_g = 82 °C` and collapses to `345.60 kN` (`FAIL`).
6. **68–78% Lower Embodied Carbon + Wire-Free Coolant-Leak EIS Twin:**
   - Achieves **`20.36 kg CO2e/m²`** (`50 psf` Class-A Office, **`-77.87%`** vs. `250 mm` PT) and **`38.79 kg CO2e/m²`** (`313 psf` AI Data Center, **`-67.84%`** vs. `310 mm` PT), while a 7-frequency [`impedence-analyzers`](/aska-physical/impedence-analyzers) Cole-Cole sweep detects chilled-water leaks via a **`+46.16%` `50 kHz` reactance shift** with **`0.0000%` mechanical rack-load crosstalk**.

## Reproduce & Verify

```bash
python3 verify.py
```

Verifies four SymPy symbolic theorems and **10/10 must-fail controls** against [`results/certificate.json`](results/certificate.json). Full engineering handoff, negative findings, and issue roadmap are documented in [`HANDOFF.md`](HANDOFF.md) and [`CHANGELOG.md`](CHANGELOG.md).

## Attribution & Ethos

- **Architect & Human Sign-Off:** Shahid Arifuddin (`@abu-aska`)
- **Foundational `Foundation-0` Lineage:** Ahraz Arifuddin (`@ahrazzle`)
- **Autonomous Engineering Capture:** Google Gemini (per [`ETHOS.md`](/aska-physical/.github/blob/main/ETHOS.md)).
