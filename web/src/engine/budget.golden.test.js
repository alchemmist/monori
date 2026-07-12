/**
 * Golden tests: the JS engine must reproduce every figure the Google Sheet
 * computed over six years of real data (reference.json), run against the
 * exact migrated snapshot (snapshot.json).
 */

import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, it, expect } from "vitest";
import { computeRange } from "./budget.js";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../migration/out");

// These golden tests run against the migrated Google Sheet data, which is
// private and gitignored (migration/out/). When those fixtures aren't present
// (e.g. in CI), skip the suite instead of failing.
const hasFixtures =
  existsSync(path.join(OUT, "snapshot.json")) && existsSync(path.join(OUT, "reference.json"));
const describeGolden = hasFixtures ? describe : describe.skip;

const snapshot = hasFixtures
  ? JSON.parse(readFileSync(path.join(OUT, "snapshot.json"), "utf8"))
  : null;
const reference = hasFixtures
  ? JSON.parse(readFileSync(path.join(OUT, "reference.json"), "utf8"))
  : {};

const kop = (rub) => Math.round(rub * 100);
const catIdByName = hasFixtures
  ? new Map(snapshot.categories.map((c) => [c.name, c.id]))
  : new Map();
const results = hasFixtures ? computeRange(snapshot, 2020, 2027) : new Map();

// Known legacy divergence, verified by hand against the sheet formulas:
// the 2021/2022 sheets used an OLD January formula that carried negative
// December balances over (no overspent reset). It bit exactly once in six
// years: Banking, Jan 2022, -30 RUB. The engine applies the current
// (conditional) rule uniformly, so:
//   - Banking 2022-01 balance: sheet -3000 kopecks, engine 0;
//   - every "available to budget" from Feb 2022 onward is shifted by +3000.
const LEGACY_BANKING = { year: 2022, month: 1, category: "Banking", sheet: -3000, engine: 0 };
const availableAdjustment = (year, month) =>
  year > 2022 || (year === 2022 && month >= 2) ? 3000 : 0;

describeGolden("engine reproduces the spreadsheet", () => {
  for (const [yearStr, yearRef] of Object.entries(reference)) {
    const year = +yearStr;
    const res = results.get(year);

    it(`${year}: per-category budgeted/outflows/balance`, () => {
      const mismatches = [];
      for (const row of yearRef.rows) {
        const catId = catIdByName.get(row.category);
        const months = res.byCategory.get(catId);
        expect(months, `category ${row.category} missing`).toBeTruthy();
        row.months.forEach((mm, i) => {
          for (const field of ["budgeted", "outflows", "balance"]) {
            let expected = kop(mm[field]);
            if (
              field === "balance" &&
              year === LEGACY_BANKING.year &&
              i + 1 === LEGACY_BANKING.month &&
              row.category === LEGACY_BANKING.category &&
              expected === LEGACY_BANKING.sheet
            ) {
              expected = LEGACY_BANKING.engine;
            }
            const got = months[i][field];
            if (expected !== got) {
              mismatches.push(
                `${row.category} ${year}-${i + 1} ${field}: sheet ${expected} engine ${got}`,
              );
            }
          }
        });
      }
      expect(mismatches).toEqual([]);
    });

    it(`${year}: monthly income totals`, () => {
      yearRef.totals.income_by_month.forEach((v, i) => {
        const expected = kop(typeof v === "number" ? v : 0);
        expect(res.income[i], `income ${year}-${i + 1}`).toBe(expected);
      });
    });

    it(`${year}: available to budget chain`, () => {
      yearRef.totals.available_by_month.forEach((v, i) => {
        const expected = kop(typeof v === "number" ? v : 0) + availableAdjustment(year, i + 1);
        expect(res.available[i], `available ${year}-${i + 1}`).toBe(expected);
      });
    });
  }
});
