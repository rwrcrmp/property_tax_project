-- Homestead Exemption Queries for Travis County Property Tax Database
-- Database: data/processed/travis_property_tax.db

-- =============================================================================
-- BASIC: Addresses with Homestead Exemption
-- =============================================================================
SELECT
    s.pID,
    s.streetNum || ' ' || COALESCE(s.streetPrefix, '') || ' ' ||
    s.streetName || ' ' || COALESCE(s.streetSuffix, '') AS address,
    s.zip,
    pr.exemptions
FROM property_situs s
JOIN property_profile pr ON s.pID = pr.pID
WHERE pr.exemptions LIKE '%HS%'
  AND s.primarySitus = 1;


-- =============================================================================
-- DETAILED: Full Property Info with Homestead Exemption
-- =============================================================================
SELECT
    p.pID,
    i.geoID,
    s.streetNum || ' ' || COALESCE(s.streetPrefix,'') || ' ' ||
    s.streetName || ' ' || COALESCE(s.streetSuffix,'') AS address,
    s.zip,
    l.legalDescription,
    pr.exemptions,
    pr.imprvActualYearBuilt AS year_built,
    pr.imprvMainArea AS sqft
FROM properties p
JOIN property_situs s ON p.pID = s.pID AND s.primarySitus = 1
JOIN property_identification i ON p.pID = i.pID
JOIN property_profile pr ON p.pID = pr.pID
JOIN property_legal_description l ON p.pID = l.pID
WHERE pr.exemptions LIKE '%HS%';


-- =============================================================================
-- COUNT: Homestead Properties by ZIP Code
-- =============================================================================
SELECT
    s.zip,
    COUNT(DISTINCT p.pID) AS homestead_count
FROM properties p
JOIN property_situs s ON p.pID = s.pID AND s.primarySitus = 1
JOIN property_profile pr ON p.pID = pr.pID
WHERE pr.exemptions LIKE '%HS%'
GROUP BY s.zip
ORDER BY homestead_count DESC;


-- =============================================================================
-- SENIOR: Over-65 Homestead Exemptions
-- =============================================================================
SELECT
    s.pID,
    s.streetNum || ' ' || COALESCE(s.streetPrefix,'') || ' ' ||
    s.streetName || ' ' || COALESCE(s.streetSuffix,'') AS address,
    s.zip,
    pr.exemptions
FROM property_situs s
JOIN property_profile pr ON s.pID = pr.pID
WHERE pr.exemptions LIKE '%OV65%'
  AND s.primarySitus = 1;


-- =============================================================================
-- REFERENCE: Common Exemption Codes
-- =============================================================================
-- HS     = Homestead
-- OV65   = Over 65
-- DP     = Disabled Person
-- DV     = Disabled Veteran
-- EX-XV  = Religious/Charitable Exemption
