// RELAY_TIMEOUT_MS from the environment: the GCP unit sets 420000 because a cold VM start adds ~90 s.
import assert from "node:assert/strict";
import { test } from "node:test";
import { timeoutFromEnv } from "../src/relay.ts";

test("timeoutFromEnv reads a positive number of milliseconds", () => {
  assert.equal(timeoutFromEnv("420000"), 420_000);
});

test("timeoutFromEnv falls back to the default when unset, empty or not a positive number", () => {
  for (const v of [undefined, "", "abc", "0", "-5"]) assert.equal(timeoutFromEnv(v), undefined, String(v));
});
