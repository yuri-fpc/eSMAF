"""The dataset of Cherubin et al. (2016), transcribed from the published paper.

Cherubin, M.R., Karlen, D.L., Franco, A.L.C., Cerri, C.E.P., Tormena, C.A.,
Cerri, C.C. (2016). A Soil Management Assessment Framework (SMAF) evaluation
of Brazilian sugarcane expansion on soil quality.
Soil Sci. Soc. Am. J. 80, 215-226. https://doi.org/10.2136/sssaj2015.09.0328

Everything here is a transcription of what the paper prints.  Nothing is
derived, averaged or adjusted: MEASURED holds their Table 2 (mean measured
values) and PUBLISHED holds their Table 3 (the SMAF scores those values
produced in the original spreadsheet).  The factor classes, crop assignments
and the pH regression are quoted from their Materials and Methods.

Units as printed in Table 2
    pH   in 0.01 mol/L CaCl2   (converted to water by the authors, see PH_WATER)
    P    mg dm-3               (ion exchange resin, van Raij et al. 2001)
    K    mg dm-3
    BD   Mg m-3                (numerically g cm-3)
    AGS  %
    SOC  g kg-1
    MBC  mg kg-1
    BG   mg p-nitrophenol kg-1 h-1
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Table 2 - mean measured values.  Key: (site, land_use, depth)
# Order: pH_CaCl2, P, K, BD, AGS, SOC, MBC, BG   (None where not measured)
# --------------------------------------------------------------------------
MEASURED: dict[tuple[str, str, str], tuple] = {
    # ---------------------------------------------------------- Lat_17S
    ("Lat_17S", "NV", "0-10"):  (4.4,  5.6,  39.8, 1.23, 90.9, 15.6,  397.2,  49.7),
    ("Lat_17S", "PA", "0-10"):  (4.3,  3.0,  23.8, 1.63, 92.8,  9.5,  301.5,  40.0),
    ("Lat_17S", "SC", "0-10"):  (5.6,  7.3,  23.8, 1.26, 73.3, 10.8,  414.8,  47.2),
    ("Lat_17S", "NV", "10-20"): (4.4,  4.5,  30.5, 1.28, 88.7, 12.9,   None,  None),
    ("Lat_17S", "PA", "10-20"): (4.4,  2.6,  19.2, 1.61, 93.3,  8.4,   None,  None),
    ("Lat_17S", "SC", "10-20"): (5.6,  7.0,  22.3, 1.54, 78.5, 10.4,   None,  None),
    ("Lat_17S", "NV", "20-30"): (4.5,  3.5,  27.0, 1.28, 88.7, 11.2,   None,  None),
    ("Lat_17S", "PA", "20-30"): (4.4,  2.5,  18.8, 1.63, 93.6,  6.4,   None,  None),
    ("Lat_17S", "SC", "20-30"): (5.4,  4.7,  18.0, 1.51, 84.4,  9.7,   None,  None),
    # ---------------------------------------------------------- Lat_21S
    ("Lat_21S", "NV", "0-10"):  (6.8, 17.3, 108.7, 1.20, 92.1, 21.8,  870.4, 122.6),
    ("Lat_21S", "PA", "0-10"):  (4.5,  7.1, 163.0, 1.53, 86.2, 13.3,  438.5, 273.2),
    ("Lat_21S", "SC", "0-10"):  (5.8, 19.6, 120.8, 1.62, 60.5, 11.1,  539.9, 200.6),
    ("Lat_21S", "NV", "10-20"): (6.7, 12.5, 113.0, 1.32, 72.8, 16.0,   None,  None),
    ("Lat_21S", "PA", "10-20"): (4.5,  3.9, 133.3, 1.65, 86.2,  9.5,   None,  None),
    ("Lat_21S", "SC", "10-20"): (5.6, 13.2, 113.8, 1.68, 69.9,  9.9,   None,  None),
    ("Lat_21S", "NV", "20-30"): (6.7,  9.9,  93.5, 1.38, 71.5, 13.1,   None,  None),
    ("Lat_21S", "PA", "20-30"): (4.5,  3.2, 120.4, 1.65, 81.7,  7.5,   None,  None),
    ("Lat_21S", "SC", "20-30"): (5.2,  7.8, 102.8, 1.68, 73.4,  8.0,   None,  None),
    # ---------------------------------------------------------- Lat_23S
    ("Lat_23S", "NV", "0-10"):  (4.3, 14.3, 109.1, 0.89, 93.8, 36.7, 1978.7, 337.8),
    ("Lat_23S", "PA", "0-10"):  (5.2, 11.5, 170.1, 1.30, 95.8, 36.4, 2085.9, 115.7),
    ("Lat_23S", "SC", "0-10"):  (5.9,  8.8, 120.4, 1.33, 84.3, 18.9,  928.6,  53.8),
    ("Lat_23S", "NV", "10-20"): (4.3, 12.4,  95.4, 1.03, 93.9, 33.7,   None,  None),
    ("Lat_23S", "PA", "10-20"): (5.1,  9.8, 174.4, 1.41, 97.2, 27.6,   None,  None),
    ("Lat_23S", "SC", "10-20"): (5.8,  8.6,  90.7, 1.44, 83.3, 18.4,   None,  None),
    ("Lat_23S", "NV", "20-30"): (4.3, 11.0,  90.3, 1.06, 92.0, 30.3,   None,  None),
    ("Lat_23S", "PA", "20-30"): (5.0,  7.6, 158.4, 1.39, 96.8, 20.6,   None,  None),
    ("Lat_23S", "SC", "20-30"): (5.9,  7.2,  77.4, 1.44, 88.0, 17.3,   None,  None),
}

# --------------------------------------------------------------------------
# Table 3 - SMAF scores published for those values.
# Order: pH, P, K, BD, AGS, SOC, MBC, BG
# --------------------------------------------------------------------------
PUBLISHED: dict[tuple[str, str, str], tuple] = {
    ("Lat_17S", "NV", "0-10"):  (0.99, 0.85, 0.44, 0.73, 1.00, 0.96, 1.00, 0.19),
    ("Lat_17S", "PA", "0-10"):  (0.50, 0.39, 0.22, 0.38, 1.00, 0.78, 0.95, 0.15),
    ("Lat_17S", "SC", "0-10"):  (0.89, 0.78, 0.29, 0.71, 1.00, 0.74, 1.00, 0.19),
    ("Lat_17S", "NV", "10-20"): (0.99, 0.77, 0.36, 0.61, 1.00, 0.88, None, None),
    ("Lat_17S", "PA", "10-20"): (0.52, 0.29, 0.18, 0.41, 1.00, 0.65, None, None),
    ("Lat_17S", "SC", "10-20"): (0.89, 0.78, 0.28, 0.32, 1.00, 0.69, None, None),
    ("Lat_17S", "NV", "20-30"): (1.00, 0.60, 0.33, 0.63, 1.00, 0.77, None, None),
    ("Lat_17S", "PA", "20-30"): (0.54, 0.26, 0.18, 0.40, 1.00, 0.40, None, None),
    ("Lat_17S", "SC", "20-30"): (0.79, 0.54, 0.23, 0.32, 1.00, 0.63, None, None),

    ("Lat_21S", "NV", "0-10"):  (0.79, 1.00, 0.68, 0.98, 1.00, 1.00, 1.00, 0.91),
    ("Lat_21S", "PA", "0-10"):  (0.63, 0.88, 0.81, 0.56, 1.00, 0.96, 1.00, 1.00),
    ("Lat_21S", "SC", "0-10"):  (0.91, 0.99, 0.71, 0.39, 1.00, 0.88, 1.00, 1.00),
    ("Lat_21S", "NV", "10-20"): (0.83, 0.98, 0.70, 0.94, 0.99, 0.98, None, None),
    ("Lat_21S", "PA", "10-20"): (0.60, 0.56, 0.75, 0.35, 1.00, 0.78, None, None),
    ("Lat_21S", "SC", "10-20"): (0.89, 0.96, 0.69, 0.33, 0.99, 0.81, None, None),
    ("Lat_21S", "NV", "20-30"): (0.82, 0.96, 0.62, 0.85, 1.00, 0.95, None, None),
    ("Lat_21S", "PA", "20-30"): (0.63, 0.43, 0.72, 0.36, 1.00, 0.54, None, None),
    ("Lat_21S", "SC", "20-30"): (0.71, 0.80, 0.65, 0.33, 0.99, 0.61, None, None),

    ("Lat_23S", "NV", "0-10"):  (0.96, 0.99, 0.79, 0.99, 1.00, 1.00, 1.00, 1.00),
    ("Lat_23S", "PA", "0-10"):  (0.96, 0.95, 0.96, 0.61, 1.00, 1.00, 1.00, 0.84),
    ("Lat_23S", "SC", "0-10"):  (0.89, 0.86, 0.84, 0.58, 1.00, 0.98, 1.00, 0.23),
    ("Lat_23S", "NV", "10-20"): (0.97, 0.99, 0.76, 0.96, 1.00, 1.00, None, None),
    ("Lat_23S", "PA", "10-20"): (0.91, 0.95, 0.97, 0.46, 1.00, 1.00, None, None),
    ("Lat_23S", "SC", "10-20"): (0.87, 0.84, 0.73, 0.39, 1.00, 0.98, None, None),
    ("Lat_23S", "NV", "20-30"): (0.97, 0.98, 0.74, 0.97, 1.00, 1.00, None, None),
    ("Lat_23S", "PA", "20-30"): (0.89, 0.87, 0.94, 0.45, 1.00, 0.99, None, None),
    ("Lat_23S", "SC", "20-30"): (0.89, 0.76, 0.67, 0.33, 1.00, 0.98, None, None),
}

INDICATOR_ORDER = ("pH", "P", "K", "BD", "AGG", "SOC", "MBC", "BG")

LAND_USE_LABEL = {
    "NV": "Native vegetation",
    "PA": "Pasture",
    "SC": "Sugarcane",
}

# --------------------------------------------------------------------------
# Crop assignment, from Table 1 (land use history) and the Materials and
# Methods.  The authors added four entries to the SMAF crop table:
# Brazilian Cerrado vegetation, Atlantic forest vegetation, Brazilian tropical
# grasses (Brachiaria spp. and Cynodon spp.) and sugarcane.  Lat_17S native
# vegetation is Cerradao (Cerrado biome); the native vegetation at Lat_21S is a
# semi-deciduous seasonal forest transitional between Atlantic forest and
# Cerrado, and Lat_23S is described as similar to Lat_21S.
# --------------------------------------------------------------------------
CROP: dict[tuple[str, str], str] = {
    ("Lat_17S", "NV"): "Brazilian cerrado",
    ("Lat_21S", "NV"): "Brazilian atlantic forest",
    ("Lat_23S", "NV"): "Brazilian atlantic forest",
    ("Lat_17S", "PA"): "Brazilian brachiaria",
    ("Lat_21S", "PA"): "Brazilian brachiaria",
    ("Lat_23S", "PA"): "Brazilian brachiaria",
    ("Lat_17S", "SC"): "Brazilian sugarcane",
    ("Lat_21S", "SC"): "Brazilian sugarcane",
    ("Lat_23S", "SC"): "Brazilian sugarcane",
}

# --------------------------------------------------------------------------
# Factor classes, quoted from the Materials and Methods.
#
#   organic matter  4 (low)                           all sites
#   climate         1 (>=170 sunny days, >=550 mm)    all sites
#   season          2 (summer, January)               all sites
#   mineralogy      3 (1:1 clay and Fe/Al oxides)     all sites
#   slope           2 (2-5 %)                         all sites
#   weathering      2 (highly weathered)              all sites
#   P method        5 (ion exchange resin)            all sites
#   texture         2 at Lat_21S and for pasture at Lat_17S;
#                   4 at Lat_17S (except pasture) and at Lat_23S
#   Fe oxide        1 at Lat_21S, 2 at the other sites
#
# region and EC method are not stated because no indicator in the dataset uses
# them: region tunes AWC and EC method tunes EC and SAR, none of which was
# measured.  eSMAF requires all eleven to be chosen, so they are set to the
# values the sites actually have (humid; the 1:1 ratio of the Brazilian
# routine) and are inert for this dataset.
#
# Texture and Fe oxide vary within Lat_17S because the pasture there sits on a
# different soil (loamy Typic Hapludox) from the native vegetation and
# sugarcane (clayey Anionic Acrudox), so the site description is split.
# --------------------------------------------------------------------------
BASE_FACTORS = dict(
    region=2, season=2, climate=1, slope=2,
    mineral=3, organic_matter=4, weathering=2,
    p_method=5, ec_method=2,
)

SITE_FACTORS: dict[str, dict[str, int]] = {
    "Lat_17S Acrudox": {**BASE_FACTORS, "texture": 4, "iron_oxide": 2},
    "Lat_17S Hapludox": {**BASE_FACTORS, "texture": 2, "iron_oxide": 2},
    "Lat_21S": {**BASE_FACTORS, "texture": 2, "iron_oxide": 1},
    "Lat_23S": {**BASE_FACTORS, "texture": 4, "iron_oxide": 2},
}

#: Which site description each (site, land use) is scored against.
SITE_OF: dict[tuple[str, str], str] = {
    ("Lat_17S", "NV"): "Lat_17S Acrudox",
    ("Lat_17S", "SC"): "Lat_17S Acrudox",
    ("Lat_17S", "PA"): "Lat_17S Hapludox",
    ("Lat_21S", "NV"): "Lat_21S",
    ("Lat_21S", "PA"): "Lat_21S",
    ("Lat_21S", "SC"): "Lat_21S",
    ("Lat_23S", "NV"): "Lat_23S",
    ("Lat_23S", "PA"): "Lat_23S",
    ("Lat_23S", "SC"): "Lat_23S",
}


def ph_water(ph_cacl2: float) -> float:
    """Ciprandi (1993), as quoted by Cherubin et al.: the regression they used
    to put pH on the water basis the SMAF curve is defined on.
    r2 = 0.97, p < 0.05."""
    return 0.890 + 0.922 * ph_cacl2


def rows() -> list[dict]:
    """One dictionary per sample, in the column names eSMAF recognises."""
    out = []
    for (site, use, depth), values in MEASURED.items():
        ph, p, k, bd, ags, soc, mbc, bg = values
        out.append({
            "site": SITE_OF[(site, use)],
            "land_use": LAND_USE_LABEL[use],
            "management": LAND_USE_LABEL[use],
            "crop": CROP[(site, use)],
            "depth": depth,
            "sample": f"{site}-{use}-{depth}",
            "pH_water": round(ph_water(ph), 3),
            "P_mg/kg": p,
            "K_mg/kg": k,
            "BD_g/cm3": bd,
            "AGG_pct": ags,
            "SOC_g/kg": soc,
            "MBC_mg/kg": mbc,
            "BG_mg/kg/h": bg,
        })
    return out
