# Changelog

## [0.1.0] - 2026-11-15
### Added
- Initialized `aska-physical/funi-floors` (`README.md`, `HANDOFF.md`, `CHANGELOG.md`, `verify.py`, `results/certificate.json`) unifying `fibral-rigidity`, `cfrp-truss`, `venturi-collars`, and `impedence-analyzers` into a modular Stay-in-Place (SIP) Self-Prestressing Funicular MEP Floor Cassette and `313 psf` (`15 kPa`) Active-Confined Column-Head Punching Collar.
- Proved three closed-form SymPy theorems (`verify_symbolic_theorems`): funicular zero-moment arch identity, Castigliano elastic arch-tie + `Fe-SMA` compatibility (`H = (H_rigid + chi*P_SMA)/(1 + chi)`), `AISC DG11` mass-stiffness crossover frequency (`f_n* = 5.7143 Hz`), and `45-deg` octagonal MEP rib-aperture shear restoration (`V_oct = sqrt(2)*A_d*f_fd`).
- Machine-verified six coupled engineering domains with `10/10` must-fail controls across `9.0 m x 9.0 m` Class-A Office (`50 psf`, `20.36 kg CO2e/m2` = `-77.87%` vs. PT) and AI Data-Center (`313 psf`, `38.79 kg CO2e/m2` = `-67.84%` vs. PT, `-73.77%` dead mass, `80.11%` flush-corner punching utilization, `3.33x` `120-min` `ISO 834` fire safety factor, `0.323 kWh/m2` Joule prestressing pulse, and `46.16%` `50 kHz` EIS coolant-leak reactance shift with `0.00%` load crosstalk).
