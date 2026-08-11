# OWDB — Architecture

This document explains what every part of OWDB is, how it works, and how the
parts feed each other. It is the map of the project: read it before deep work
anywhere in the repository, and read the section for a subsystem before changing
that subsystem.

It is written to be read start-to-finish once, and grepped thereafter. Every
file is named by its literal repo-relative path, every section opens with a
one-line summary, and every paragraph stands on its own — so landing in the
middle of this document, whether by scrolling or by search, still lands you in
context.

`README.md`, `FEATURES.md`, and `SPEC.md` remain the long-form references for
ingest, features, and the capture design respectively. This document sits above
them and says how everything connects.

## Contents

- [0. Orientation](#0-orientation)
- [1. The map](#1-the-map)
- [2. Repository tour](#2-repository-tour)
- [3. Ingest — `faceit_sync`](#3-ingest--faceit_sync)
- [4. Dashboard build](#4-dashboard-build)
- [5. Capture — the Python `owdb` package](#5-capture--the-python-owdb-package)
- [6. Browser capture app](#6-browser-capture-app)
- [7. Scrims](#7-scrims)
- [8. Infrastructure and CI](#8-infrastructure-and-ci)
- [9. Data contracts](#9-data-contracts)
- [10. Lifecycles and operations](#10-lifecycles-and-operations)
- [11. Glossary](#11-glossary)
- [12. Invariants](#12-invariants)
- [13. Testing map](#13-testing-map)

---

## 0. Orientation

What OWDB is, and where to look for the thing you want to change.

## 1. The map

Every artifact in the system, who writes it, and who reads it.

## 2. Repository tour

Every top-level directory and root file, and whether it is live, reference, generated, or local-only.

## 3. Ingest — `faceit_sync`

How FACEIT League match data gets into a local SQLite database, and the data-quality hazards that shape the design.

## 4. Dashboard build

How the live site at `docs/index.html` is assembled from static parts, and why a single JavaScript error blanks the page.

## 5. Capture — the Python `owdb` package

How hero compositions are read off the Overwatch observer HUD and turned into typed, stored observations.

## 6. Browser capture app

The zero-install capture tool at `docs/capture/` — the only supported capture path.

## 7. Scrims

The private, browser-local side channel for scrim data, and the separate page that reads it.

## 8. Infrastructure and CI

What runs outside this repository: the Cloudflare Worker and the GitHub Actions workflow that is the sole writer of the live site.

## 9. Data contracts

The exact shape of every file that crosses a subsystem boundary.

## 10. Lifecycles and operations

The recurring procedures: code wipes, season cutover, and deploying each piece.

## 11. Glossary

The project's vocabulary, defined once.

## 12. Invariants

Rules that must not be broken, each with the failure mode it prevents.

## 13. Testing map

Which tests guard which subsystem, and the commands that prove nothing is broken.
