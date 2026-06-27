# Homestead Exemption Fraud in Austin Short-Term Rentals
### A Preliminary Investigation and Case for Further Research

---

## The Problem

Texas law grants homeowners a homestead exemption on their primary residence — a meaningful reduction in assessed property value for tax purposes. In Travis County, this exemption can reduce a property's taxable value by tens of thousands of dollars annually. The legal requirement is straightforward: the property must be the owner's principal place of residence. You cannot legally claim a homestead exemption on a property you do not live in.

Short-term rental operators who rent out entire homes — not spare rooms, but the whole property — are, by definition, not living there as their primary residence. Yet there is reason to believe a meaningful share of these operators continue to claim the homestead exemption, either through oversight, inertia, or deliberate fraud.

The result is a quiet tax subsidy for commercial rental activity, paid for by every other Travis County property taxpayer.

---

## Why This Is Worth Investigating

Austin has experienced rapid growth in short-term rental activity over the past decade, driven by platforms like Airbnb and VRBO. The City of Austin requires STR operators to register with the city, and the Texas Tax Code requires homeowners to notify the appraisal district if they cease using a property as their primary residence. In practice, there is little apparent coordination between these two systems, and no systematic cross-referencing of STR permits against homestead exemption rolls.

Travis County Appraisal District (TCAD) manages the homestead exemption database. The City of Austin manages STR permits. These datasets sit in separate administrative silos. Nobody appears to be routinely checking whether a property on one list should be disqualified from the other.

The scale of potential revenue loss is non-trivial. If even a few hundred properties are fraudulently claiming the exemption, the annual tax impact across all applicable taxing entities (county, city, school district, etc.) could run into the millions of dollars.

---

## The Data

This analysis draws on three publicly available datasets:

**1. Travis County Appraisal District (TCAD) Property Tax Export**
A full export of Travis County parcel data, including property characteristics, ownership, assessed value, and exemption status. This is the authoritative source for identifying which properties claim a homestead exemption and which are classified as single-family residential.

**2. City of Austin STR Permit Records**
The City of Austin maintains a public registry of licensed short-term rental operators. The dataset includes approximately 2,400 registered permits as of 2025-2026, with property addresses obfuscated to block-level for privacy (e.g., "BLOCK OF 2400 DORMARION LN"). Permits are categorized by type:
- **Type 1**: Owner-occupied primary residence rental (a subset of rooms or periods)
- **Type 1-Secondary / 1-A**: Secondary unit on an owner-occupied property
- **Type 2 Residential**: Whole-home rental, non-owner-occupied — the primary fraud signal
- **Type 3**: Commercial or multi-unit properties

**3. Inside Airbnb Listings Data**
A third-party scrape of active Airbnb listings for the Austin market, including latitude/longitude coordinates and listing characteristics. This dataset captures a broader picture of the de facto STR market, including properties that may not be registered with the city.

---

## The Hypothesis

Properties operating as whole-home short-term rentals (Type 2 permits, or Airbnb listings marked as "entire home") should not qualify for the homestead exemption. Neighborhoods with elevated STR activity — particularly whole-home rentals — should, if the tax rolls are accurate, show *lower* homestead exemption rates among single-family properties.

If instead we observe that STR-dense neighborhoods show *higher* homestead exemption rates than comparable non-STR neighborhoods, that is a statistical signal worth investigating at the parcel level.

---

## The Approach

Rather than attempting to match individual properties directly (which the block-level address obfuscation makes difficult), this analysis uses a neighborhood-level spatial aggregation strategy.

The study area is divided into a grid of hexagonal cells using Uber's H3 geospatial indexing system — a standard tool for this type of analysis. At the chosen resolution, each hexagon covers roughly 0.7 square kilometers, approximating a neighborhood scale with enough parcels per cell to produce statistically stable ratios.

For each hexagonal cell, two ratios are computed from TCAD data:

> **Homestead Rate** = (SFR parcels with homestead exemption) ÷ (all SFR parcels)

> **STR Rate** = (registered STR permits or Airbnb whole-home listings) ÷ (all SFR parcels)

These ratios are then compared spatially. The prediction under the null hypothesis — no fraud — is that these two rates should be uncorrelated or weakly negatively correlated: STR-heavy neighborhoods should have lower homestead exemption rates, because those operators don't live there.

A positive correlation between the two rates is the anomaly. It suggests that STR operators in those neighborhoods are, in aggregate, still claiming the exemption.

The full implementation — scripts, data sources, pipeline stages, and output specifications — is documented in `docs/project_plan.md`.

---

## What the Inside Airbnb Data Adds

The city permit dataset, while official, almost certainly undercounts actual STR activity. Mandatory registration is only as good as its enforcement, and there is limited public evidence that enforcement is systematic.

The Inside Airbnb data, which captures actual active listings regardless of permit status, allows for a registration gap analysis: neighborhoods where Airbnb listing density far exceeds permit density are likely enforcement blind spots. If those same neighborhoods also show elevated homestead exemption rates, the case for further investigation becomes substantially stronger.

---

## Limitations and Honest Caveats

This is a neighborhood-level, aggregate analysis — it identifies areas of concern, not individual violators. No property owner is accused of fraud by this analysis alone.

Block-level address obfuscation in the permit data introduces geocoding uncertainty of roughly one city block per observation. This is acceptable at neighborhood scale but precludes parcel-level matching without better data.

The STR permit dataset represents registered operators only. The true population of STR operators includes an unknown number of unregistered properties. This analysis treats the permit data as a lower bound on STR activity in each neighborhood.

Correlation between the two rates, while suggestive, does not prove fraud. There are legitimate reasons a neighborhood could have both high homestead exemption rates and high STR activity — for example, if most STRs in that area are Type 1 (owner-occupied, primary residence). The analysis filters for whole-home rental types, but misclassification in the permit data is possible.

---

## Preliminary Results

The pipeline has been run against the full TCAD dataset (486,859 parcels), City of Austin STR permits (987 Type 2 permits), and Inside Airbnb listings (7,082 active entire-home listings). After applying inclusion thresholds, 246 hex cells are retained for analysis.

**Key findings:**

- Homestead rate vs. Airbnb density: **r = −0.143** (Pearson), **p = 0.025** — a statistically significant but weak negative correlation at the neighborhood level. The direction is consistent with the hypothesis; the weakness is expected given the ecological aggregation.
- Airbnb density vs. registration gap: **r = 0.744** — strong, as expected. Denser STR neighborhoods have proportionally more unregistered listings.
- The single highest-gap hex cell (downtown Austin) has **242 more Airbnb listings than STR permits**, with a homestead rate of 62% — normal for residential stock, suggesting the fraud signal is diluted by neighboring compliant properties at this spatial scale.
- County-wide, there are **7,082 active Airbnb entire-home listings** against **987 Type 2 STR permits** — a raw registration gap of roughly 6,000 units.

The weak aggregate correlation is not a negative finding — it is the expected result of applying a neighborhood-level lens to a parcel-level phenomenon. It confirms that the free public data can identify *where* to look, but not *who* to audit.

---

## The Case for Investment

This preliminary analysis is designed to establish spatial patterns at the neighborhood level and identify candidate areas for parcel-level auditing. It is not, on its own, an enforcement tool.

The next step — matching individual STR-permitted or Airbnb-listed properties to specific parcels claiming homestead exemptions — requires either: (a) the full, unobfuscated STR permit addresses (available to the city, not the public), or (b) a more sophisticated geocoding and parcel-matching pipeline using the Airbnb latitude/longitude data against TCAD parcel boundaries.

Both are tractable with modest investment. The potential revenue recovery — and the deterrent effect of a credible audit process — likely justifies the cost many times over.

