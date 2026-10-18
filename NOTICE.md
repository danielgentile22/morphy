# Data notices and attribution

The [MIT license](LICENSE) covers the code in this repository only. It does not cover any of
the data the code works with.

No source data is redistributed here. The `data/` directory is git-ignored, and the data TUI
(`python -m data_tui`) pulls each dataset directly from its publisher. Anyone who runs the
pipeline gets the data under the publisher's own terms, listed below. The one data file in the
repo is a Census Bureau county boundary file, covered at the end.

The terms below were checked against each publisher's terms page or embedded dataset metadata
on 2026-10-18. Where a page could not be fetched, the entry says so. Nothing here is legal
advice. Per-source schemas and automation policies are in
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Owner names and takedown requests

Parcel owner names and mailing addresses come from public records published by state and
county agencies. They are public field by field, but together they identify people, so the
project treats them as personal data ([docs/SECURITY.md](docs/SECURITY.md)). The public demo
shows them only inside the app, behind a session, with no export or bulk download.

To ask for a name or record to be removed from the demo, open an issue at
<https://github.com/danielgentile22/morphy/issues>. Corrections to the underlying record
belong with the county or state publisher.

## Parcels

### Arkansas statewide parcels

- **Publisher:** Arkansas GIS Office.
- **Terms:** <https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/MapServer/6/metadata>
- **What the terms say:** "This dataset may be downloaded and utilized in any manner." The data
  is provided "as is" and "for information purposes" only.
- **Disclaimer:** Under Arkansas Code §15-21-504, parcel data is not a legal boundary
  description.
- **Credit:** none required. Source: Arkansas GIS Office.

### Florida Department of Revenue tax roll parcels

- **Publisher:** Florida Department of Revenue, Property Tax Oversight.
- **Terms:** <https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx>
  (readme: <https://floridarevenue.com/property/dataportal/Documents/PTO%20Data%20Portal/Map%20Data/Parcel%20Shapefiles%20Readme.pdf>)
- **What the terms say:** the rolls are published under chapter 119, Florida Statutes (the state
  public records law). There is no separate license.
- **Owner-name note:** records exempt under section 119.071, Florida Statutes, are left out of the
  Name-Address-Legal (NAL) files. Only a current roll should be served, so an owner protected
  after an older roll was published is not exposed.
- **Credit:** Source: Florida Department of Revenue, Property Tax Oversight.

### Florida state-owned land parcels

- **Publisher:** Florida Department of Environmental Protection, Division of State Lands,
  distributed by the Florida Geographic Data Library.
- **Terms:** <https://www.geoplan.ufl.edu/agol/metadata/xml/dsl_parcel_composite.xml>
- **Credit:** FL-DEP-DSL, GIS Land Records Mapping Project staff.
- **Required disclaimer:** the metadata asks that any redistribution carry a similar disclaimer.
  This data is intended to be used as a geo-spatial index and relative location reference
  only. It is not intended for boundary determination.

### Montana Cadastral

- **Publisher:** Montana State Library, Montana Cadastral Framework.
- **Terms:** <https://gisservice.mt.gov/ArcGIS/rest/services/msdi_cadastral_map_v1/MapServer/info/iteminfo?f=pjson>
- **What the terms say:** provided "as a convenience to the public," with no copyright or
  license restriction on display.
- **Owner-name note:** the metadata cites Montana Code §2-6-1017, which restricts using an
  agency-prepared list of names and addresses as a mailing or distribution list. The app shows
  owners per parcel and offers no list export.
- **Credit:** Source: Montana State Library, Montana Cadastral Framework.

### West Virginia statewide parcels

- **Publisher:** WV GIS Technical Center and the West Virginia State Tax Department, via
  Map West Virginia.
- **Terms:** <https://www.mapwv.gov/terms.html> (dataset: <https://wvgis.wvu.edu/data/dataset.php?ID=371>)
- **What the terms say:** anyone may "view, copy or distribute information found here without
  obligation to Map West Virginia," unless a specific item says otherwise.
- **Credit:** Source: WV GIS Technical Center / WV State Tax Department.

### North Carolina parcels (not in the demo)

- **Publisher:** NC OneMap.
- **Source:** <https://www.nconemap.gov/datasets/nconemap::north-carolina-parcels-polygons>
- North Carolina was deferred. Its data is not composed and is not on the demo.

## Towers and infrastructure

### FCC Antenna Structure Registration and Universal Licensing System

- **Publisher:** Federal Communications Commission.
- **Source:** <https://www.fcc.gov/wireless/data/public-access-files-database-downloads>
- **Terms:** a work of the United States government, public domain under 17 U.S.C. §105. The
  FCC website policy page could not be fetched to confirm.
- **Credit:** Source: FCC.

### FAA Digital Obstacle File

- **Publisher:** Federal Aviation Administration.
- **Source:** <https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dof/>
- **Terms:** a work of the United States government, public domain. Not part of the
  2026-10-18 terms review.
- **Credit:** Source: FAA.

### EIA Form 860 and 860M

- **Publisher:** U.S. Energy Information Administration.
- **Source:** <https://www.eia.gov/electricity/data/eia860/>
- **Terms:** <https://www.eia.gov/about/copyrights_reuse.php>. Public domain. Not part of the
  2026-10-18 terms review.
- **Credit:** Source: U.S. Energy Information Administration.

### U.S. Large-Scale Solar Photovoltaic Database (USPVDB)

- **Publisher:** U.S. Geological Survey and Lawrence Berkeley National Laboratory.
- **Terms:** <https://eerscmap.usgs.gov/uspvdb/> (digital object identifier: <https://doi.org/10.5066/P9IA3TUS>)
- **What the terms say:** "free and in the public domain … There are no restrictions."
- **Requested acknowledgement:**

  > Map services and data are available from Large-Scale Solar Photovoltaic Database, provided
  > by the U.S. Geological Survey and Lawrence Berkeley National Laboratory via
  > https://energy.usgs.gov/uspvdb

### FDOT outdoor advertising permits (not in the demo)

- **Publisher:** Florida Department of Transportation.
- **Terms:** <https://www.fdot.gov/agencyresources/webpoliciesandnotices.shtm>
- A Florida public record under chapter 119, provided for "informational purposes only." The
  source is registered but was never wired into the composites.

## Economic distress overlays

### HUD Opportunity Zones and Qualified Census Tracts

- **Publisher:** U.S. Department of Housing and Urban Development.
- **Source:** <https://www.arcgis.com/home/item.html?id=ef143299845841f8abb95969c01f88b5>
  (Opportunity Zones) and <https://www.arcgis.com/home/item.html?id=f55f80843c9a436ba8e578a54cdd8cea>
  (Qualified Census Tracts).
- **Terms:** a federal work. The metadata carries a no-warranty disclaimer only.
- **Credit:** U.S. Department of Housing and Urban Development, U.S. Census Bureau.

### USDA persistent poverty counties

- **Publisher:** U.S. Department of Agriculture, Economic Research Service.
- **Source:** <https://www.ers.usda.gov/data-products/county-typology-codes>
- **Terms:** a federal work under 17 U.S.C. §105. The policies page has no reuse wording.
- **Credit:** Source: USDA Economic Research Service.

### Appalachian Regional Commission county economic status

- **Publisher:** Appalachian Regional Commission.
- **Source:** <https://www.arc.gov/distressed-designation-and-county-economic-status-classification-system/>
- **Terms:** presumed public domain as a federal-state commission's work. No terms page was
  found to confirm.
- **Credit:** Source: Appalachian Regional Commission.

## Not used as data

### Steel-in-the-Air lease rates

- **Publisher:** Steel in the Air, Inc.
- **Terms:** <https://www.steelintheair.com/sita_terms_of_use-disclosures/>
- Its content is proprietary. The terms forbid reproducing, distributing or creating
  derivative works without written consent, except limited attributed quotation for
  non-commercial informational purposes. The project read it by hand as a reference benchmark
  only. None of its data is in the repo, the pipeline or the demo.

## Bundled in this repository

### Census cartographic boundary file

- **File:** `scripts/preprocess/assets/cb_2023_us_county_20m.zip` (2023 county boundaries,
  1:20,000,000 scale).
- **Publisher:** U.S. Census Bureau.
- **Source:** <https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html>
- **Terms:** public domain, a work of the United States government.
- **Credit:** Source: U.S. Census Bureau.
