# Study: Exact-$\mathbb{Q}$ Checkerboard Live-Load Arch Bending (`Issue #1`), MEP-Hole Bracing & Carbon End-Interlock Audit (`Issue #3`)

- **Evidence Classification (`aska-physical/dock#8`):** **`MODEL` / `CHECKER`** (pure Python 3 standard library exact rational arithmetic; `0` floats; `0` bare `assert`s; not a physical bench measurement — per Issue `#3`, final sleeve length and wedge angle remain to be settled by physical anchor pull-out tests).
- **Pinned Upstream Reference:** `aska-physical/funi-floors @ 00eba18ceea0adf69f7dc12ca47d151622faa32a` (`verify.py:47-110,280-282`, Issues `#1` & `#3`).
- **Scope:** Strictly add-only companion study under `studies/checkerboard-bracing-and-interlock-audit/` (`0` edits to `verify.py` or `results/certificate.json`).

## Certified Exact-$\mathbb{Q}$ Results (`MODEL` / `CHECKER`)

1. **Part A — Half-Span Checkerboard Load (`Issue #1`, `15 kPa / 0 kPa` on `9 m x 3 m`, `f = 0.285 m`) & MEP Web Bracing:**
   - **Exact Quarter-Span Bending Theorem:** Decomposing left/right loading directly in $\mathbb{Q}$ proves exact zero crown moment ($M(L/2) = 0$) and exact quarter-span bending $M(L/4) = +w_{\mathrm{asym}} L^2 / 64 = \mathbf{3645/64\text{ kN}\cdot\text{m}}$ ($\approx 56.953\text{ kN}\cdot\text{m}$) with inter-cassette shear-key demand $V_{\mathrm{key}} = 405/8\text{ kN}$ (`50.625 kN`).
   - **Must-Fail Control (Un-ribbed `55 mm` Thin Shell):** Symmetric `15/15 kPa` stays centered ($e = 0$), whereas half-span `15/0 kPa` pushes thrust eccentricity to **`285/5552 m` ($\approx 51.33\text{ mm}$)** — exceeding both the middle-third kern (`9.17 mm`) and the entire `55 mm` shell half-depth (`27.5 mm`, **`FAIL`**).
   - **Pass Control (`380 mm` Ribbed & Braced Cassette):** Eccentricity `51.33 mm` stays strictly inside the `380 mm` middle-third kern (`63.33 mm`, **`PASS`**), and Maxwell–Calladine rank-nullity proves unbraced MEP cutouts carry `4` floppy modes (`shear_energy = 0`) vs. alternating half-density diagonals (`shear_energy = 2`) and full $45^\circ$ octagonal web bracing (`0` floppy modes).
2. **Part B — Carbon End-Interlock Anchor Pull (`Issue #3`, `700 kN` per Rib End):**
   - Single `480 kN` dowel falls short of `700 kN` rib demand; uniform `4`-pin load sharing (`175 kN <= 260 kN`) masks Volkersen lead-pin peaking (**`275 kN > 260 kN`**, **`FAIL`**).
   - End-dense graded `4`-pin spacing (`[1/6, 2/3, 1/6]` of `400 mm` sleeve) drops peak pin load to **`245 kN <= 260 kN`** while holding net rib ligament tear capacity at `720 kN >= 700 kN` (**`PASS`**, zero extra holes).
   - Over-perforating to `6` pins (`60%` hole ratio) drops net-section tear capacity to `480 kN < 700 kN` (**`FAIL`**).

## Reproduce & Verify

```bash
cd studies/checkerboard-bracing-and-interlock-audit
for flags in "-I -B" "-I -O -B" "-I -B -W error"; do
  python3 $flags funi_floors_bio_audit.py --check funi_floors_bio_certificate.json
  python3 $flags test_funi_floors_bio_r5.py
done
```
