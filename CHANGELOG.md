# Changelog

## 1.2.0 — 2026-10-07

- Show enclosed gap sizes in a sortable, localized Area (m²) column.
- Convert projected CRS units to square metres; measure geographic CRS gaps on their ellipsoid.
- Preserve numeric `area_m2` values in CSV, GeoPackage and temporary layers, including when reprojecting exports.
- Refresh the English screenshot to show a selected 40,000 m² gap.
- Verify 48 integration tests in each English/Hungarian and QGIS 3.44.9/4.2.2 combination.

## 1.1.0 — 2026-10-07

- Follow the QGIS interface language: English or Hungarian, with English fallback for other languages.
- Translate controls, rule descriptions, validation errors, run messages and generated export text.
- Keep saved rule IDs, layer names, JSON keys and export columns independent of language.
- Add a complete Hungarian Qt translation catalog with safe placeholder formatting and translator cleanup.
- Add English screenshots, English and Hungarian documentation, and a portable example project.
- Verify 43 integration tests in each English/Hungarian and QGIS 3.44.9/4.2.2 combination.
- Provide installable plugin and demo ZIPs with SHA-256 checksums.

## 1.0.0 — 2026-10-07

- Initial Hungarian interface with nine topology rules.
- Searchable layer selectors, saved rule sets, background tasks, filtered results and map highlighting.
- CSV, GeoPackage and temporary issue-layer output.
- Support for QGIS 3.44 and Qt6-based QGIS 4.
