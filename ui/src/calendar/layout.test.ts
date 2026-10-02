import { test } from "node:test";
import assert from "node:assert/strict";
import { addDays, dayName, daysCovered, genevaParts, hhmm, layoutColumns, monthGrid, rangeFor, segmentFor, shift, startOfWeek, title, weekday } from "./layout.ts";

test("weekdays start on Monday", () => {
  assert.equal(weekday("2026-10-05"), 0);          // Monday
  assert.equal(weekday("2026-10-11"), 6);          // Sunday
  assert.equal(dayName("2026-10-02"), "Friday");
  assert.equal(startOfWeek("2026-10-02"), "2026-09-28");
  assert.equal(startOfWeek("2026-10-04"), "2026-09-28");   // Sunday belongs to the week that began on the 28th
  assert.equal(startOfWeek("2026-10-05"), "2026-10-05");
});

test("date arithmetic crosses months, years and leap days", () => {
  assert.equal(addDays("2026-10-31", 1), "2026-11-01");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2028-02-28", 1), "2028-02-29");
  assert.equal(addDays("2026-03-01", -1), "2026-02-28");
});

test("the month grid is six full weeks, Monday first, containing the whole month", () => {
  const g = monthGrid("2026-10-15");
  assert.equal(g.length, 42);
  assert.equal(g[0], "2026-09-28");                // Oct 1 2026 is a Thursday; the grid starts on the Monday before
  assert.equal(weekday(g[0]), 0);
  assert.ok(g.includes("2026-10-01") && g.includes("2026-10-31"));
  assert.equal(g[41], "2026-11-08");
  const feb = monthGrid("2027-02-10");              // Feb 1 2027 is a Monday: grid starts that day
  assert.equal(feb[0], "2027-02-01");
});

test("ranges per view", () => {
  assert.deepEqual(rangeFor("day", "2026-10-02"), { start: "2026-10-02", end: "2026-10-02" });
  assert.deepEqual(rangeFor("week", "2026-10-02"), { start: "2026-09-28", end: "2026-10-04" });
  assert.deepEqual(rangeFor("month", "2026-10-02"), { start: "2026-09-28", end: "2026-11-08" });
});

test("moving between periods never skips a month", () => {
  assert.equal(shift("month", "2026-10-31", 1), "2026-11-01");
  assert.equal(shift("month", "2026-03-31", -1), "2026-02-01");
  assert.equal(shift("month", "2026-12-15", 1), "2027-01-01");
  assert.equal(shift("week", "2026-10-02", 1), "2026-10-09");
  assert.equal(shift("day", "2026-10-01", -1), "2026-09-30");
});

test("titles", () => {
  assert.equal(title("month", "2026-10-02"), "October 2026");
  assert.equal(title("day", "2026-10-02"), "Friday 2 October 2026");
  assert.equal(title("week", "2026-10-07"), "5–11 October 2026");
  assert.equal(title("week", "2026-10-02"), "28 Sep – 4 Oct 2026");
});

test("instants are shown in Geneva time whatever the browser's zone", () => {
  assert.deepEqual(genevaParts("2026-10-02T09:30:00+02:00"), { date: "2026-10-02", minutes: 9 * 60 + 30 });
  assert.deepEqual(genevaParts("2026-10-02T07:30:00Z"), { date: "2026-10-02", minutes: 9 * 60 + 30 });          // summer time: UTC+2
  assert.deepEqual(genevaParts("2026-12-02T07:30:00Z"), { date: "2026-12-02", minutes: 8 * 60 + 30 });          // winter time: UTC+1
  assert.deepEqual(genevaParts("2026-10-02T23:30:00Z"), { date: "2026-10-03", minutes: 90 });                  // crosses midnight in Geneva
  assert.equal(hhmm(9 * 60 + 5), "09:05");
});

test("which days an event covers", () => {
  assert.deepEqual(daysCovered({ start: "2026-10-07", end: "2026-10-10", all_day: true }), ["2026-10-07", "2026-10-08", "2026-10-09"]);   // end is exclusive
  assert.deepEqual(daysCovered({ start: "2026-10-12", end: "2026-10-13", all_day: true }), ["2026-10-12"]);
  assert.deepEqual(daysCovered({ start: "2026-10-12", end: null, all_day: true }), ["2026-10-12"]);
  assert.deepEqual(daysCovered({ start: "2026-10-05T09:00:00+02:00", end: "2026-10-05T10:00:00+02:00", all_day: false }), ["2026-10-05"]);
  assert.deepEqual(daysCovered({ start: "2026-10-03T22:00:00+02:00", end: "2026-10-04T06:00:00+02:00", all_day: false }), ["2026-10-03", "2026-10-04"]);
  assert.deepEqual(daysCovered({ start: "2026-10-03T22:00:00+02:00", end: "2026-10-04T00:00:00+02:00", all_day: false }), ["2026-10-03"]);   // ends exactly at midnight
  assert.deepEqual(daysCovered({ start: "2026-10-05T09:00:00+02:00", end: null, all_day: false }), ["2026-10-05"]);
});

test("the slice of a timed event on a given day", () => {
  const e = { start: "2026-10-05T09:00:00+02:00", end: "2026-10-05T10:30:00+02:00", all_day: false };
  assert.deepEqual(segmentFor(e, "2026-10-05"), { startMin: 540, endMin: 630 });
  assert.equal(segmentFor(e, "2026-10-06"), null);
  assert.equal(segmentFor({ start: "2026-10-07", end: "2026-10-08", all_day: true }, "2026-10-07"), null);        // all-day events have no time slice
  const night = { start: "2026-10-03T22:00:00+02:00", end: "2026-10-04T06:00:00+02:00", all_day: false };
  assert.deepEqual(segmentFor(night, "2026-10-03"), { startMin: 1320, endMin: 1440 });
  assert.deepEqual(segmentFor(night, "2026-10-04"), { startMin: 0, endMin: 360 });
  assert.deepEqual(segmentFor({ start: "2026-10-05T09:00:00+02:00", end: "2026-10-05T09:05:00+02:00", all_day: false }, "2026-10-05"), { startMin: 540, endMin: 560 });   // too short: given a readable height
  assert.deepEqual(segmentFor({ start: "2026-10-05T09:00:00+02:00", end: null, all_day: false }, "2026-10-05"), { startMin: 540, endMin: 570 });
});

test("overlapping events sit side by side; separate ones keep the full width", () => {
  const m = layoutColumns([
    { id: 1, startMin: 540, endMin: 600 }, { id: 2, startMin: 560, endMin: 620 }, { id: 3, startMin: 600, endMin: 650 },   // 1-2 overlap, 2-3 overlap, 1-3 touch (3 starts when 1 ends)
    { id: 4, startMin: 700, endMin: 760 },                                                                                  // alone
    { id: 5, startMin: 760, endMin: 800 },                                                                                  // starts exactly when 4 ends
  ]);
  assert.deepEqual(m.get(1), { col: 0, cols: 2 });
  assert.deepEqual(m.get(2), { col: 1, cols: 2 });
  assert.deepEqual(m.get(3), { col: 0, cols: 2 });                                  // fits in lane 0 after event 1 ended at 600
  assert.deepEqual(m.get(4), { col: 0, cols: 1 });
  assert.deepEqual(m.get(5), { col: 0, cols: 1 });
  assert.equal(layoutColumns([]).size, 0);
});

test("three simultaneous events get three columns", () => {
  const m = layoutColumns([{ id: 1, startMin: 600, endMin: 660 }, { id: 2, startMin: 600, endMin: 660 }, { id: 3, startMin: 600, endMin: 660 }]);
  assert.deepEqual([...m.values()].map((x) => x.cols), [3, 3, 3]);
  assert.deepEqual(new Set([...m.values()].map((x) => x.col)), new Set([0, 1, 2]));
});
