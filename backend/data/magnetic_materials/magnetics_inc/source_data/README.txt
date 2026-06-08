MAGNETICS INC POWDER CORE — STEINMETZ COEFFICIENT DATABASE
Source: Magnetics Inc 2025 Powder Core Catalog, Pages 108-109
Formula: P_L = a x B^b x f^c
Units: P_L in mW/cm3, B in Tesla (T), f in kilohertz (kHz)
Scope: Toroid geometries only
Date extracted: 2025-05-30
Method: Text extraction from PDF (pdftotext), manually verified
         against catalog comparison table (page 28) — all within +/-5%

MATERIALS COVERED:
  edge, high_flux, mpp, kool_mu, kool_mu_max
  kool_mu_hf, kool_mu_ultra, xflux, xflux_ultra

NOTES:
- Kool Mu Ultra has frequency-split coefficients (<100kHz vs >100kHz)
  CSVs store <100kHz which applies to PFC at 70kHz
  >100kHz coefficients are in the JSON files (hi_freq_a/b/c fields)
- Missing permeabilities (kool_mu_ultra 90/125, xflux_ultra 40/90/125)
  use nearest-group coefficients from the catalog table
- EDGE-60 has a Step-13 validation anchor in edge_60.json
  Catalog fit gives Pcore=0.928W vs Step-13 reference 1.125W (-18%)
  This is expected: catalog fit covers 1-500mT; Step-13 fitted at 30-60mT
