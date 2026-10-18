"""Curated explainer glossary: plain-language definitions of every complex
term the platform shows, with formulas, units, where each term is used, and
references. Deterministic reference data — no LLM involvement, no fabrication.
The frontend Explainer highlights these terms inline and links findings to
their explanations.
"""

CATEGORY_ORDER = ["stellar", "cosmology", "celestial", "observation",
                   "statistics", "methods"]

GLOSSARY: list[dict] = [
    # --- stellar -----------------------------------------------------------
    {
        "id": "hr-diagram",
        "term": "Hertzsprung–Russell diagram",
        "aka": ["HR diagram", "H-R diagram"],
        "category": "stellar",
        "short": "A plot of stellar luminosity vs temperature — the map of stellar evolution.",
        "explain": (
            "Every star is placed by how bright it is (luminosity, vertical) versus how hot "
            "its surface is (temperature, horizontal, traditionally reversed so hot is left). "
            "Stars are not scattered randomly: most sit on a diagonal band called the main "
            "sequence, and as a star ages it moves off that band. Plotting a star's track "
            "here is how astronomers see its evolutionary state at a glance."
        ),
        "formula": "x = T_eff (reversed, log scale); y = L (log scale)",
        "units": ["K", "L☉"],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["teff", "luminosity", "main-sequence", "isochrone"],
        "references": ["Hertzsprung (1911); Russell (1913) — original diagrams"],
    },
    {
        "id": "teff",
        "term": "Effective temperature (T_eff)",
        "aka": ["Teff", "T_eff", "surface temperature"],
        "category": "stellar",
        "short": "The temperature a star's surface radiates at, set by its luminosity and size.",
        "explain": (
            "A star glows like a hot object at some temperature — that is its effective "
            "temperature, the single temperature that reproduces its total brightness if the "
            "whole surface radiated uniformly. The Sun is about 5772 K (yellow-white); blue "
            "O-stars exceed 30,000 K; cool red M-dwarfs sit near 3000 K. Spectral classes "
            "O-B-A-F-G-K-M are just temperature bins, hot to cool."
        ),
        "formula": "L = 4π R² σ T_eff⁴  (Stefan–Boltzmann law)",
        "units": ["K"],
        "where_used": ["Stellar Lab", "Paper → Simulation", "Observation Explorer"],
        "see_also": ["hr-diagram", "luminosity", "spectral-class"],
        "references": ["Gray, D. F. 2005, 'The Observation and Analysis of Stellar Photospheres'"],
    },
    {
        "id": "luminosity",
        "term": "Luminosity (L)",
        "aka": ["L_sun", "L☉", "absolute power"],
        "category": "stellar",
        "short": "The total energy a star radiates per second — its true power output.",
        "explain": (
            "Luminosity is the star's actual power (like a light bulb's wattage), not how "
            "bright it looks from Earth (that is apparent magnitude, which depends on "
            "distance). It is usually expressed relative to the Sun: L = 1 is solar "
            "luminosity (3.828×10²⁶ watts); Sirius A shines ~25× brighter."
        ),
        "formula": "L/L☉ = (R/R☉)² (T_eff/T_eff,☉)⁴",
        "units": ["L☉", "W"],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["teff", "hr-diagram", "mass-luminosity"],
        "references": ["IAU nominal solar quantities (Mamajek et al. 2015)"],
    },
    {
        "id": "main-sequence",
        "term": "Main sequence",
        "aka": ["MS", "hydrogen burning"],
        "category": "stellar",
        "short": "The stable phase where a star fuses hydrogen into helium in its core.",
        "explain": (
            "A star spends ~90% of its life on the main sequence: gravity's squeeze is exactly "
            "balanced by energy from hydrogen fusion (hydrostatic equilibrium). Its position "
            "along the sequence is set almost entirely by mass — massive stars are hot and "
            "brilliant but burn out fast; low-mass stars are cool and can shine for trillions "
            "of years. When core hydrogen runs out, the star leaves the sequence."
        ),
        "formula": "t_MS ≈ 10 Gyr (M/M☉)^-2.5  (rule of thumb)",
        "units": ["Gyr"],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["ms-lifetime", "zams", "mass-luminosity"],
        "references": ["Kippenhahn, Weigert & Weiss 2012, 'Stellar Structure and Evolution', Ch. 18"],
    },
    {
        "id": "zams",
        "term": "Zero-age main sequence (ZAMS)",
        "aka": ["ZAMS"],
        "category": "stellar",
        "short": "The moment a star first settles onto the main sequence and starts burning hydrogen steadily.",
        "explain": (
            "Before the ZAMS a star is contracting and heating up (a protostar). The ZAMS is "
            "the point where hydrogen fusion becomes stable and the star reaches equilibrium — "
            "its 'birth certificate' on the HR diagram. In this platform's track data the ZAMS "
            "is identified as the point of maximum surface gravity along each evolutionary track."
        ),
        "formula": "ZAMS ≡ argmax(log g) along the track (proxy used here)",
        "units": ["yr"],
        "where_used": ["Stellar Lab"],
        "see_also": ["main-sequence", "isochrone"],
        "references": ["Dotter 2016, ApJS 222, 8 (EEP definitions)"],
    },
    {
        "id": "ms-end",
        "term": "Main-sequence end (turnoff)",
        "aka": ["MS end", "turnoff", "TAMS"],
        "category": "stellar",
        "short": "When core hydrogen runs out and the star starts evolving into a giant.",
        "explain": (
            "The moment hydrogen fusion in the core stops, the star leaves the main sequence "
            "and swells into a subgiant/giant. On an HR diagram the population's 'turnoff "
            "point' is a clock: the most massive star still on the sequence tells you how old "
            "a star cluster is. Here the MS end is flagged with a luminosity proxy: the first "
            "track point exceeding 1.3× the ZAMS luminosity."
        ),
        "formula": "MS end ≡ first point with L > 1.3 · L_ZAMS (proxy)",
        "units": ["yr"],
        "where_used": ["Stellar Lab"],
        "see_also": ["zams", "isochrone", "main-sequence"],
        "references": ["Salaris & Cassisi 2005, 'Evolution of Stars and Stellar Populations'"],
    },
    {
        "id": "isochrone",
        "term": "Isochrone",
        "aka": ["equal-age line"],
        "category": "stellar",
        "short": "The curve joining stars of the same age but different masses on the HR diagram.",
        "explain": (
            "Iso means 'equal'; chronos means 'time'. Because massive stars age faster, a "
            "population born together spreads across the HR diagram in a characteristic shape: "
            "low-mass stars still sit on the main sequence while massive ones have moved off "
            "it. An isochrone is that snapshot curve — astronomers match observed cluster "
            "colors to isochrones to date the cluster. Here isochrones are computed from "
            "published PARSEC tracks at a chosen age."
        ),
        "formula": "isochrone(t) = { (T_eff(m,t), L(m,t)) : m ∈ grid }",
        "units": ["Gyr"],
        "where_used": ["Stellar Lab"],
        "see_also": ["zams", "ms-end", "parsec-tracks"],
        "references": ["Bressan et al. 2012, MNRAS 427, 127 (PARSEC isochrones)"],
    },
    {
        "id": "metallicity",
        "term": "Metallicity (Z)",
        "aka": ["Z", "Z_sun", "fraction of heavy elements"],
        "category": "stellar",
        "short": "The fraction of a star made of elements heavier than helium.",
        "explain": (
            "Astronomers call every element heavier than helium a 'metal'. Z is the mass "
            "fraction of those metals: the Sun has Z ≈ 0.014 (1.4%), while stars born in the "
            "early universe can be 10–100× poorer. Metallicity changes how a star's atmosphere "
            "absorbs light and how fast it evolves — metal-poor isochrones shift toward hotter "
            "temperatures. Comparing stellar metallicity across the galaxy maps its chemical "
            "history."
        ),
        "formula": "Z ≡ Σ (mass fractions of elements heavier than He)",
        "units": ["dimensionless"],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["parsec-tracks", "isochrone"],
        "references": ["Asplund et al. 2009, ARA&A 47, 481 (solar composition)"],
    },
    {
        "id": "parsec-tracks",
        "term": "PARSEC evolution tracks",
        "aka": ["PARSEC v1.2S", "Padova tracks"],
        "category": "stellar",
        "short": "Published stellar evolution models computed by the Padova group.",
        "explain": (
            "PARSEC (PAdova and TRieste Stellar Evolution Code) computes how stars of different "
            "masses and compositions change over their lifetimes — temperature, luminosity, "
            "radius at every age. These are numerical models solving the equations of stellar "
            "structure, far more detailed than analytic estimates. This platform bundles the "
            "published EEP-matched PARSEC v1.2S tracks and interpolates locally, so results "
            "carry full provenance (source, release, citations) instead of being a black box."
        ),
        "formula": "outputs: (T_eff, L, R, log g, M_current)(age | M_init, Z)",
        "units": [],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["eep", "isochrone", "metallicity"],
        "references": ["Bressan et al. 2012, MNRAS 427, 127; Chen et al. 2014, MNRAS 444, 2525"],
    },
    {
        "id": "eep",
        "term": "Equal evolutionary phases (EEP)",
        "aka": ["EEP-matched tracks"],
        "category": "stellar",
        "short": "Standardized waypoints along evolution tracks so different stars can be compared point-by-point.",
        "explain": (
            "Raw stellar models output unevenly spaced timesteps — hard to interpolate or "
            "compare. The EEP scheme divides each star's life into equal evolutionary phases "
            "(pre-MS, MS, MS turnoff, giant, …) so corresponding points line up across masses. "
            "It is the reason tracks here can be interpolated smoothly and assembled into "
            "isochrones without artifacts."
        ),
        "formula": "mapping: age → EEP index (monotonic per phase segment)",
        "units": [],
        "where_used": ["Stellar Lab"],
        "see_also": ["parsec-tracks", "isochrone"],
        "references": ["Dotter 2016, ApJS 222, 8; Paxton et al. 2019, ApJS 243, 10 (MESA)"],
    },
    {
        "id": "spectral-class",
        "term": "Spectral class",
        "aka": ["OBAFGKM"],
        "category": "stellar",
        "short": "The letter code (O, B, A, F, G, K, M) classifying a star by its surface temperature.",
        "explain": (
            "A star's spectral class is its temperature bin: O and B are hot blue stars "
            "(>10,000 K), A/F white, G yellow like the Sun (5200–6000 K), K orange, M cool red "
            "(<3700 K). The classic mnemonic 'Oh Be A Fine Guy/Girl, Kiss Me' runs hot to cool. "
            "Originally assigned by hydrogen-line strength, it is now understood as a "
            "temperature sequence. Subclasses 0–9 give finer steps, e.g. the Sun is G2."
        ),
        "formula": "O>30000K · B 10–30k · A 7.5–10k · F 6–7.5k · G 5.2–6k · K 3.7–5.2k · M <3.7k",
        "units": ["K"],
        "where_used": ["Stellar Lab", "Observation Explorer"],
        "see_also": ["teff", "main-sequence"],
        "references": ["Kleiman 1993, AJ 105, 1303 (KM93 main-sequence bands)"],
    },
    {
        "id": "mass-luminosity",
        "term": "Mass–luminosity relation",
        "aka": ["L ∝ M^3.5"],
        "category": "stellar",
        "short": "More massive main-sequence stars are dramatically brighter.",
        "explain": (
            "For stars burning hydrogen, luminosity scales steeply with mass — roughly L ∝ M^3.5 "
            "for solar-type stars. Doubling a star's mass makes it ~11× brighter, which is why "
            "massive stars live fast and die young: they have more fuel but burn it "
            "proportionally faster. This relation is the engine behind everything on the main "
            "sequence and the reason 'small' changes in mass produce large changes in lifetime."
        ),
        "formula": "L ∝ M^n, n ≈ 3.5 (solar branch); piecewise for very low/high mass",
        "units": ["L☉", "M☉"],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["main-sequence", "ms-lifetime", "luminosity"],
        "references": ["Salaris & Cassisi 2005, Ch. 2; Kippenhahn et al. 2012, Ch. 18"],
    },
    {
        "id": "ms-lifetime",
        "term": "Main-sequence lifetime",
        "aka": ["stellar lifetime", "t_MS"],
        "category": "stellar",
        "short": "How long a star can burn hydrogen before running out of core fuel.",
        "explain": (
            "Available nuclear fuel divided by burn rate: t ~ ηMc²/L, where η≈0.7% of hydrogen "
            "rest mass converts to energy. Because L rises steeply with mass, lifetime falls "
            "steeply too — the Sun will shine ~10 Gyr total, while a 10 M☉ star lives under "
            "30 million years. This is the number that decides whether a star is still alive "
            "at any given cosmic epoch."
        ),
        "formula": "t_MS ≈ η M c² / L ≈ 10 Gyr (M/M☉)^-2.5",
        "units": ["Gyr"],
        "where_used": ["Stellar Lab", "Paper → Simulation"],
        "see_also": ["main-sequence", "mass-luminosity"],
        "references": ["Kippenhahn et al. 2012, Ch. 18; Salaris & Cassisi 2005"],
    },
    # --- cosmology ----------------------------------------------------------
    {
        "id": "redshift",
        "term": "Redshift (z)",
        "aka": ["z"],
        "category": "cosmology",
        "short": "How much the universe has stretched light from a distant source since it was emitted.",
        "explain": (
            "As space expands, light traveling through it stretches — its wavelength grows, "
            "shifting toward red. Redshift z measures that stretch: z = 0 today, z = 1 means "
            "the wavelength has doubled (light emitted when the universe was half its current "
            "size). Because expansion is smooth, redshift doubles as a lookback clock and a "
            "distance indicator: higher z = further away and further back in time."
        ),
        "formula": "z = (λ_observed − λ_emitted) / λ_emitted",
        "units": ["dimensionless"],
        "where_used": ["Cosmology Lab", "Observation Explorer", "Paper → Simulation"],
        "see_also": ["comoving-distance", "luminosity-distance", "lambda-cdm"],
        "references": ["Hogg 1999, astro-ph/9905116 (distance measures in cosmology)"],
    },
    {
        "id": "hubble-constant",
        "term": "Hubble constant (H₀)",
        "aka": ["H0", "H_0"],
        "category": "cosmology",
        "short": "The present-day expansion rate of the universe.",
        "explain": (
            "H₀ sets how fast galaxies recede per unit distance today (~70 km/s per Mpc: a "
            "galaxy 1 Mpc away slides away at ~70 km/s). Its inverse sets the universe's age "
            "scale (~1/H₀ ≈ 14 Gyr). It is also the center of a famous tension: early-universe "
            "measurements (Planck CMB) give ~67.4, while local distance-ladder measurements "
            "(SH0ES supernovae) give ~73 — a real, unresolved discrepancy this platform can "
            "reproduce on both sides."
        ),
        "formula": "v = H₀ · d  (Hubble–Lemaître law, local universe)",
        "units": ["km s⁻¹ Mpc⁻¹"],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["lambda-cdm", "luminosity-distance", "redshift"],
        "references": ["Riess et al. 2022, ApJL 934, L7 (SH0ES); Planck Collab. 2020, A&A 641, A6"],
    },
    {
        "id": "omega-m",
        "term": "Matter density (Ω_m)",
        "aka": ["Omega_m", "Ω_m"],
        "category": "cosmology",
        "short": "The fraction of the universe's total energy density that is matter.",
        "explain": (
            "Ω_m is the universe's matter content as a fraction of the 'critical density' needed "
            "for flat geometry: about 0.315 — of which ordinary atoms are only ~5%, the rest "
            "being dark matter. It governs how much expansion has decelerated over time: more "
            "matter means stronger early braking. The remaining ~0.685 is dark energy (Ω_Λ), "
            "which accelerates expansion instead."
        ),
        "formula": "Ω_m ≡ ρ_matter / ρ_critical; flat universe: Ω_m + Ω_Λ = 1",
        "units": ["dimensionless"],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["lambda-cdm", "friedmann-equation", "hubble-constant"],
        "references": ["Planck Collab. 2020, A&A 641, A6"],
    },
    {
        "id": "lambda-cdm",
        "term": "ΛCDM (Lambda-CDM)",
        "aka": ["LCDM", "standard cosmological model"],
        "category": "cosmology",
        "short": "The standard model of cosmology: cold dark matter + dark energy in an expanding universe.",
        "explain": (
            "Λ (Lambda) is Einstein's cosmological constant — dark energy driving accelerating "
            "expansion. CDM is cold dark matter: slow-moving, invisible mass whose gravity "
            "sculpts galaxies and clusters. Together with general relativity they form the "
            "successful standard model: it explains the cosmic microwave background, the "
            "growth of structure, and distance–redshift data with just six parameters. It "
            "reigns because it works — but the Hubble tension hints at cracks."
        ),
        "formula": "components: baryons + CDM + Λ (+ radiation at early times)",
        "units": [],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["omega-m", "friedmann-equation", "hubble-constant"],
        "references": ["Planck Collab. 2020, A&A 641, A6; Baumann 2012, astro-ph/0907.5462"],
    },
    {
        "id": "friedmann-equation",
        "term": "Friedmann equations",
        "aka": ["Friedmann equation", "expansion equation"],
        "category": "cosmology",
        "short": "General relativity's equations for how the universe's size changes over time.",
        "explain": (
            "Derived by Alexander Friedmann in 1922 from Einstein's field equations, they relate "
            "the expansion rate H = ȧ/a to the universe's contents: (H/H₀)² = Ω_m(1+z)³ + "
            "Ω_Λ (+ radiation term at high z). Solve it forward and you get the whole expansion "
            "history — how distances, ages, and lookback times depend on redshift. Everything "
            "the Cosmology Lab computes traces back to this equation."
        ),
        "formula": "(H/H₀)² = Ω_m(1+z)³ + Ω_r(1+z)⁴ + Ω_Λ",
        "units": ["km s⁻¹ Mpc⁻¹"],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["lambda-cdm", "omega-m", "comoving-distance"],
        "references": ["Friedmann 1922, Z. Phys. 10, 377; Durrer 2007, arXiv:0711.0154"],
    },
    {
        "id": "comoving-distance",
        "term": "Comoving distance (D_C)",
        "aka": ["comoving", "D_C"],
        "category": "cosmology",
        "short": "Distance that grows only with expansion — like coordinates printed on a stretching map.",
        "explain": (
            "Two galaxies riding the expansion together keep the same comoving distance forever, "
            "even as their actual (proper) separation grows. Comoving distance factors out the "
            "expansion so astronomers can compare positions across cosmic time; all other "
            "distance measures (luminosity, angular diameter) derive from it by simple factors "
            "of redshift."
        ),
        "formula": "D_C = (c/H₀) ∫₀ᶻ dz'/E(z');  D_L = (1+z)D_C;  D_A = D_C/(1+z)",
        "units": ["Mpc"],
        "where_used": ["Cosmology Lab"],
        "see_also": ["luminosity-distance", "friedmann-equation", "redshift"],
        "references": ["Hogg 1999, astro-ph/9905116"],
    },
    {
        "id": "luminosity-distance",
        "term": "Luminosity distance (D_L)",
        "aka": ["D_L"],
        "category": "cosmology",
        "short": "The distance inferred from how faint a standard candle appears.",
        "explain": (
            "In an expanding universe, an object's light is diluted by 1/(4πD_L²) AND its "
            "photons are stretched (each losing energy by 1+z) AND arrival rate drops by 1+z — "
            "so D_L grows faster than the naive distance: D_L = (1+z) × comoving distance. "
            "Astronomers measure D_L by observing standard candles (Type Ia supernovae) and "
            "comparing true vs apparent brightness — this is exactly how the SH0ES H₀ value "
            "is measured."
        ),
        "formula": "D_L = (1+z) (c/H₀) ∫₀ᶻ dz'/E(z')",
        "units": ["Mpc"],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["comoving-distance", "hubble-constant", "distance-modulus"],
        "references": ["Hogg 1999, astro-ph/9905116"],
    },
    {
        "id": "distance-modulus",
        "term": "Distance modulus (μ)",
        "aka": ["mu", "μ = m − M"],
        "category": "cosmology",
        "short": "The difference between apparent and absolute magnitude — a logarithmic distance.",
        "explain": (
            "Comparing how bright a candle looks (apparent magnitude m) to how bright it truly "
            "is (absolute magnitude M) gives its distance in magnitudes: μ = m − M = "
            "5 log₁₀(d/10 pc). Because magnitudes are logarithmic, each +5 marks 10× the "
            "distance. Supernova Hubble diagrams are literally plots of μ versus redshift."
        ),
        "formula": "μ = m − M = 5 log₁₀(d_L/10 pc)",
        "units": ["mag"],
        "where_used": ["Cosmology Lab", "Observation Explorer"],
        "see_also": ["luminosity-distance", "redshift"],
        "references": ["Hogg 1999, astro-ph/9905116"],
    },
    {
        "id": "age-of-universe",
        "term": "Age of the universe",
        "aka": ["cosmic age"],
        "category": "cosmology",
        "short": "How much time has passed since the Big Bang — computed from the expansion history.",
        "explain": (
            "Integrating the Friedmann equation from today back to infinite density gives the "
            "time elapsed: about 13.8 Gyr for Planck parameters. The age depends on the "
            "expansion history — with more dark energy the universe accelerated, so it is "
            "older than a pure-matter model of the same H₀ would suggest. Globular cluster "
            "ages and the CMB independently confirm this number."
        ),
        "formula": "t₀ = ∫₀^∞ dz / [(1+z) H(z)]",
        "units": ["Gyr"],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["friedmann-equation", "hubble-constant", "lambda-cdm"],
        "references": ["Planck Collab. 2020, A&A 641, A6 (13.797 ± 0.023 Gyr)"],
    },
    # --- celestial ----------------------------------------------------------
    {
        "id": "n-body",
        "term": "N-body simulation",
        "aka": ["N-body", "N-body integration"],
        "category": "celestial",
        "short": "Numerically integrating the gravitational dance of many masses at once.",
        "explain": (
            "With two bodies (like the Earth–Sun pair) gravity has an exact formula; with three "
            "or more there is none — the motion must be computed step by step: at each tiny "
            "timestep, sum every pair's gravitational pull, nudge velocities and positions, "
            "repeat. REBOUND, the integrator here, also tracks conservation laws (energy, "
            "angular momentum) as honesty checks: if those drift, the numerics are failing."
        ),
        "formula": "a_i = −Σ_{j≠i} G m_j (r_i − r_j)/|r_i − r_j|³",
        "units": [],
        "where_used": ["Celestial Simulator", "Paper → Simulation"],
        "see_also": ["kepler-third-law", "energy-drift", "conservation-check"],
        "references": ["Rein & Liu 2012, A&A 537, A128 (IAS15 integrator)"],
    },
    {
        "id": "eccentricity",
        "term": "Eccentricity (e)",
        "aka": ["e", "orbital eccentricity"],
        "category": "celestial",
        "short": "How stretched an orbit is: 0 = circle, →1 = long thin ellipse.",
        "explain": (
            "Eccentricity measures an orbit's departure from a perfect circle. Earth's orbit is "
            "nearly circular (e ≈ 0.017); Halley's Comet is a stretched ellipse (e ≈ 0.967). "
            "In multi-body systems, close passes pump eccentricity up — a planet's e "
            "increasing over a simulation is the earliest warning that its orbit is being "
            "destabilized, which is exactly what the stability sweep here measures."
        ),
        "formula": "e = (r_aphelion − r_perihelion)/(r_aphelion + r_perihelion)",
        "units": ["dimensionless"],
        "where_used": ["Celestial Simulator", "Paper → Simulation"],
        "see_also": ["semi-major-axis", "kepler-third-law"],
        "references": ["Murray & Dermott 1999, 'Solar System Dynamics', Ch. 1"],
    },
    {
        "id": "semi-major-axis",
        "term": "Semi-major axis (a)",
        "aka": ["a", "orbital radius", "AU"],
        "category": "celestial",
        "short": "Half the long diameter of an orbit — its average 'size'.",
        "explain": (
            "The semi-major axis is the standard size measure of an ellipse: half the longest "
            "diameter. For a circular orbit it is just the radius. Earth sits at 1 AU (about "
            "150 million km); Jupiter at 5.2 AU. Together with the central mass it fixes the "
            "orbital period via Kepler's third law — which is how exoplanet distances are "
            "inferred from observed periods."
        ),
        "formula": "a = (r_max + r_min)/2;  1 AU = 1.496×10⁸ km",
        "units": ["AU"],
        "where_used": ["Celestial Simulator", "Paper → Simulation"],
        "see_also": ["kepler-third-law", "eccentricity"],
        "references": ["Murray & Dermott 1999, Ch. 1"],
    },
    {
        "id": "kepler-third-law",
        "term": "Kepler's third law",
        "aka": ["P² ∝ a³"],
        "category": "celestial",
        "short": "Orbital period squared grows with orbital size cubed.",
        "explain": (
            "Kepler found in 1619 that P² = 4π²a³/(GM): double an orbit's size and its period "
            "grows by 2√2 ≈ 2.8×. Newton later showed the right side includes the central "
            "mass — so measuring a planet's period and distance actually weighs its star. "
            "Everywhere in this platform a period–distance consistency check is this law at "
            "work, including when interpreting exoplanet papers."
        ),
        "formula": "P² = 4π² a³ / (G M)",
        "units": ["yr", "AU", "M☉"],
        "where_used": ["Celestial Simulator", "Paper → Simulation"],
        "see_also": ["semi-major-axis", "n-body"],
        "references": ["Murray & Dermott 1999, Eq. 2.43"],
    },
    {
        "id": "energy-drift",
        "term": "Energy drift",
        "aka": ["ΔE/E₀", "relative energy error"],
        "category": "celestial",
        "short": "How much a simulation's conserved energy has wandered — a numerical accuracy gauge.",
        "explain": (
            "In an isolated gravitational system total energy never changes — any drift in the "
            "simulation is pure numerical error. 'Energy drift' reports the worst relative "
            "change seen during the run; small values (like 10⁻¹²) mean exquisite accuracy, "
            "large values mean the orbit picture cannot be trusted. The IAS15 integrator used "
            "here achieves near machine-precision conservation even through close encounters."
        ),
        "formula": "max |ΔE/E₀| over all timesteps",
        "units": ["dimensionless"],
        "where_used": ["Celestial Simulator"],
        "see_also": ["conservation-check", "n-body"],
        "references": ["Rein & Liu 2012, A&A 537, A128"],
    },
    {
        "id": "conservation-check",
        "term": "Conservation-law validation",
        "aka": ["conservation checks"],
        "category": "celestial",
        "short": "Testing that energy and angular momentum stay fixed — physics' built-in lie detector.",
        "explain": (
            "Gravity in isolation conserves energy and angular momentum, period. A simulation "
            "that violates either is wrong — full stop — no matter how plausible its plots "
            "look. That makes conservation the ultimate validation tool: every simulation here "
            "is automatically checked against these invariants, and the results are persisted "
            "with pass/fail evidence rather than taken on faith."
        ),
        "formula": "checks: |ΔE/E₀| < tol_E;  |ΔL/L₀| < tol_L",
        "units": [],
        "where_used": ["Celestial Simulator", "Validation"],
        "see_also": ["energy-drift", "n-body"],
        "references": ["Goldstein, Poole & Safko, 'Classical Mechanics', Ch. 1"],
    },
    # --- observation --------------------------------------------------------
    {
        "id": "parallax",
        "term": "Parallax",
        "aka": ["stellar parallax", "π"],
        "category": "observation",
        "short": "The tiny wobble in a star's position as Earth orbits the Sun — a direct distance measurement.",
        "explain": (
            "Hold a finger at arm's length and blink between eyes: it shifts against the "
            "background. Earth's orbit gives astronomers two vantage points 2 AU apart, so "
            "nearby stars shift slightly against distant ones. That angle is the parallax — "
            "halve it, invert it, and distance falls out in parsecs (par-sec: parallax of one "
            "arcsecond = 3.26 light-years). Gaia measures parallaxes to micro-arcsecond "
            "precision, anchoring the entire cosmic distance ladder."
        ),
        "formula": "d[pc] = 1 / π[arcsec]",
        "units": ["mas", "arcsec", "pc"],
        "where_used": ["Observation Explorer"],
        "see_also": ["cone-search", "cross-match"],
        "references": ["Gaia Collab. 2021, A&A 649, A1 (DR3); Bailer-Jones 2015, PASP 127, 994"],
    },
    {
        "id": "cone-search",
        "term": "Cone search",
        "aka": ["cone search", "position query"],
        "category": "observation",
        "short": "Asking an archive 'what catalog objects lie within this circle on the sky?'",
        "explain": (
            "The simplest astronomical database query: give a center (RA, Dec) and a radius, "
            "get every catalogued object inside that cone of sky. It is how you go from a "
            "known coordinate — say, a galaxy's location — to all cross-identified sources "
            "around it in Gaia, VizieR, SIMBAD, or the exoplanet archive. Everything in the "
            "Observation Explorer builds on this primitive."
        ),
        "formula": "SELECT ... WHERE CONTAINS(POINT('ICRS',ra,dec), CIRCLE(...)) = 1",
        "units": ["arcsec"],
        "where_used": ["Observation Explorer"],
        "see_also": ["cross-match", "parallax"],
        "references": ["IVOA Cone Search 1.03 standard"],
    },
    {
        "id": "cross-match",
        "term": "Cross-matching",
        "aka": ["crossmatch", "catalog matching"],
        "category": "observation",
        "short": "Pairing up objects seen by different surveys at (nearly) the same sky position.",
        "explain": (
            "Each telescope catalog is a separate list. To study an object fully you must join "
            "them: find the Gaia source nearest your SIMBAD target within a tolerance radius. "
            "The tolerance matters — too tight and you miss matches (proper motion shifted the "
            "position); too loose and you pair stars with the wrong neighbors. This platform "
            "reports separation distances for every match so users judge quality themselves."
        ),
        "formula": "match if angular separation < tolerance (typically 1–5 arcsec)",
        "units": ["arcsec"],
        "where_used": ["Observation Explorer"],
        "see_also": ["cone-search", "parallax"],
        "references": ["Pineau et al. 2020, A&A 638, A64 (cross-match methods)"],
    },
    {
        "id": "light-curve",
        "term": "Light curve",
        "aka": ["photometric time series"],
        "category": "observation",
        "short": "A star's brightness plotted over time — where transits, spots, and variability hide.",
        "explain": (
            "Measure a star's brightness repeatedly and you get a light curve: flat when the "
            "star is steady, dipping when a planet crosses in front, oscillating when it pulses "
            "or a spot rotates into view. Analyzing light curves found thousands of exoplanets "
            "(Kepler, TESS) and most known variable stars. Periodograms extract hidden "
            "clockwork — repeating cycles — from noisy data."
        ),
        "formula": "output: {t_i, mag_i}; periodogram → power vs frequency",
        "units": ["mag", "days"],
        "where_used": ["Observation Explorer"],
        "see_also": ["periodogram"],
        "references": ["Kovács et al. 1989, A&AS 70, 609 (Lomb–Scargle)"],
    },
    {
        "id": "periodogram",
        "term": "Periodogram",
        "aka": ["Lomb–Scargle periodogram"],
        "category": "observation",
        "short": "A 'which rhythm?' detector for unevenly sampled brightness data.",
        "explain": (
            "Like a Fourier transform but built for astronomers' gappy, unevenly timed "
            "observations: it tests every candidate frequency and reports how much periodic "
            "signal the data contains at each. The highest peak is the best-fit period — the "
            "planet's year, the binary's orbit, the variable star's pulse. Side peaks and "
            "aliases are harmonics or sampling artifacts, which is why astronomers inspect "
            "the full periodogram, not just its tallest line."
        ),
        "formula": "P(f) ∝ (χ²_mean − χ²_f) / χ²_mean  (Lomb–Scargle)",
        "units": ["cycles/day", "Hz"],
        "where_used": ["Observation Explorer"],
        "see_also": ["light-curve"],
        "references": ["Lomb 1976, Ap&SS 39, 447; Scargle 1982, ApJ 263, 835"],
    },
    {
        "id": "fits",
        "term": "FITS format",
        "aka": ["FITS file", "Flexible Image Transport System"],
        "category": "observation",
        "short": "Astronomy's universal data file: images or tables plus a self-describing header.",
        "explain": (
            "FITS is the standard file format for astronomical data — every telescope "
            "deliverable, from Hubble images to spectrograph tables. Its defining feature is "
            "the ASCII header preceding the data: instrument, coordinates, exposure time, "
            "filter, units — enough metadata to interpret the numbers without external "
            "documentation. Astropy, used here, reads FITS natively."
        ),
        "formula": "structure: HEADER (cards, 80 chars) + DATA (image/table)",
        "units": [],
        "where_used": ["Observation Explorer"],
        "see_also": ["cone-search"],
        "references": ["Pence et al. 2010, A&A 524, A42 (FITS 3.0 standard)"],
    },
    # --- statistics/methods --------------------------------------------------
    {
        "id": "mcmc",
        "term": "MCMC sampling",
        "aka": ["Markov chain Monte Carlo", "MCMC", "emcee"],
        "category": "statistics",
        "short": "Exploring parameter space by random walk to find which values fit the data.",
        "explain": (
            "When a model has several free parameters (like H₀ and Ω_m) and the data has noise, "
            "you cannot just 'solve' for the best values — you must map the landscape of "
            "plausible ones. MCMC spawns walkers that wander parameter space, stepping toward "
            "regions that fit the data better. Their accumulated path forms the posterior "
            "distribution: not one answer but the full probability landscape. More time "
            "sampling = sharper picture; the acceptance fraction measures health of the walk."
        ),
        "formula": "acceptance = accepted steps / total steps (target ~0.2–0.5)",
        "units": [],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["posterior", "credible-interval"],
        "references": ["Goodman & Weare 2010, Comm. App. Math. 63, 133; Foreman-Mackey et al. 2013, PASP 125, 306 (emcee)"],
    },
    {
        "id": "posterior",
        "term": "Posterior distribution",
        "aka": ["posterior"],
        "category": "statistics",
        "short": "The probability of each parameter value after seeing the data — the answer as a distribution.",
        "explain": (
            "Bayes' theorem turns prior beliefs plus data into a posterior: for each candidate "
            "parameter value, how probable is it given everything observed? The posterior is "
            "the honest final answer — a bell-shaped landscape, not a single number. Its peak "
            "is the most likely value; its width is the uncertainty. In cosmology, the "
            "posterior for H₀ from CMB data barely overlaps the one from supernovae — that "
            "non-overlap IS the Hubble tension."
        ),
        "formula": "P(θ|data) ∝ P(data|θ) · P(θ)  (Bayes)",
        "units": [],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["mcmc", "credible-interval"],
        "references": ["Gelman et al., 'Bayesian Data Analysis', Ch. 2"],
    },
    {
        "id": "credible-interval",
        "term": "Credible interval",
        "aka": ["CI", "68% CI", "CI68"],
        "category": "statistics",
        "short": "The range containing X% of the posterior probability — the Bayesian error bar.",
        "explain": (
            "Reading an error bar off the posterior: the 68% credible interval is the narrowest "
            "range holding 68% of the probability mass (≈ ±1σ for a Gaussian). Plain-language "
            "reading: given the data and model, the true value has a 68% chance of lying in "
            "that range. (The frequentist 'confidence interval' sounds similar but means "
            "something subtly different — this platform uses Bayesian credible intervals.)"
        ),
        "formula": "CI68 = [percentile₁₆(θ), percentile₈₄(θ)] of posterior",
        "units": [],
        "where_used": ["Cosmology Lab", "Paper → Simulation"],
        "see_also": ["posterior", "mcmc"],
        "references": ["Gelman et al., 'Bayesian Data Analysis', Ch. 4"],
    },
    # --- methods -------------------------------------------------------------
    {
        "id": "provenance",
        "term": "Provenance",
        "aka": ["data lineage", "source tracking"],
        "category": "methods",
        "short": "The documented origin of every number: where it came from and how it was computed.",
        "explain": (
            "Scientific results are only as trustworthy as their inputs. 'Provenance' is this "
            "platform's commitment to attaching the full lineage to every output: which archive "
            "or dataset served the data, which release, which citations, which interpolation or "
            "model produced the number you see. If a figure cannot say exactly where it came "
            "from, it does not belong in science — so everything here can."
        ),
        "formula": "",
        "units": [],
        "where_used": ["Everywhere"],
        "see_also": ["evidence", "model-fidelity"],
        "references": ["Silva et al. 2013, 'Provenance for Scientific Workflows'"],
    },
    {
        "id": "evidence",
        "term": "Evidence trail",
        "aka": ["tool evidence", "executed-tool proof"],
        "category": "methods",
        "short": "Machine-checked proof that an agent actually ran a tool — not just claimed it did.",
        "explain": (
            "AI agents can hallucinate plausible nonsense. To prevent that, every agent node "
            "here must return evidence: the exact tool called, its arguments, and a summary of "
            "what it actually returned. The orchestration framework rejects any node that "
            "produces no evidence, so findings on this platform are anchored to executed code "
            "— each number traceable to the tool that computed it."
        ),
        "formula": "",
        "units": [],
        "where_used": ["Research Workspace", "Agent Coordination"],
        "see_also": ["provenance", "model-fidelity"],
        "references": ["Platform design (NOESIS AI orchestration)"],
    },
    {
        "id": "model-fidelity",
        "term": "Model fidelity",
        "aka": ["fidelity label", "SIMPLIFIED ANALYTIC vs PUBLISHED TRACK"],
        "category": "methods",
        "short": "How detailed (and how trustworthy) the model behind a number is — always labeled.",
        "explain": (
            "Not all models are equal. A quick analytic estimate (like L ∝ M^3.5) is fast and "
            "rough; a published numerical track (PARSEC) solves the full stellar structure "
            "equations and is far more accurate. Every result here carries a fidelity label — "
            "SIMPLIFIED ANALYTIC, PUBLISHED TRACK, or engine output — so you always know which "
            "ladder rung a number stands on, and never mistakes a sketch for a photograph."
        ),
        "formula": "",
        "units": [],
        "where_used": ["Everywhere"],
        "see_also": ["provenance", "evidence"],
        "references": ["Platform design (NOESIS AI labeling policy)"],
    },
]


def glossary_payload() -> dict:
    return {
        "terms": GLOSSARY,
        "categories": CATEGORY_ORDER,
        "n_terms": len(GLOSSARY),
        "note": ("Curated plain-language explanations of the technical terms used "
                 "across this platform. Click any highlighted term in the UI to see "
                 "its explanation; every entry cites its scientific source."),
    }


def _match_keys(term: dict) -> list[str]:
    """All strings worth matching for one entry: term (and its pre-paren head),
    plus every alias. Single-character aliases are excluded (they fire on every
    'z' or 'e' in prose)."""
    keys = []
    head = term["term"].split("(", 1)[0].strip()
    for s in (term["term"], head, *term.get("aka", [])):
        s = s.strip()
        if len(s) >= 2 and s not in keys:
            keys.append(s)
    return keys


def find_terms(text: str) -> list[dict]:
    """Locate glossary terms inside arbitrary text (findings, messages, captions).

    Deterministic, order-independent: candidates are claimed longest-first so
    'Hubble constant' wins over 'constant'-length fragments; matches must sit on
    word boundaries; a single trailing plural 's' is consumed so 'isochrones'
    still highlights 'isochrone'. Overlapping earlier claims win. The frontend
    mirrors this algorithm for inline highlighting.
    """
    if not text:
        return []
    low = text.lower()
    claimed: list[tuple[int, int]] = []
    matches: list[dict] = []
    candidates: list[tuple[str, dict]] = []
    for t in GLOSSARY:
        for k in _match_keys(t):
            candidates.append((k.lower(), t))
    candidates.sort(key=lambda c: -len(c[0]))

    for key, term in candidates:
        start = 0
        while True:
            i = low.find(key, start)
            if i < 0:
                break
            start = i + 1
            j = i + len(key)
            # consume a plural trailing 's' when it ends at a word boundary
            if j < len(low) and low[j] == "s" and (j + 1 >= len(low) or not low[j + 1].isalnum()):
                j += 1
            # word-boundary check (unicode-aware: Λ, ⊙, ₀ are not letters here)
            if i > 0 and low[i - 1].isalnum():
                continue
            if j < len(low) and low[j].isalnum():
                continue
            if any(i < b and a < j for a, b in claimed):
                continue
            claimed.append((i, j))
            matches.append({
                "id": term["id"], "term": term["term"], "category": term["category"],
                "short": term["short"], "explain": term["explain"],
                "formula": term.get("formula", ""),
                "where_used": term.get("where_used", []),
                "references": term.get("references", []),
                "start": i, "end": j, "matched": text[i:j],
            })
    matches.sort(key=lambda m: m["start"])
    return matches
