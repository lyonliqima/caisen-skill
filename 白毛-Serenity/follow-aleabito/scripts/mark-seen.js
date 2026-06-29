#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const USER_DIR = join(homedir(), ".follow-aleabito");
const STATE_PATH = join(USER_DIR, "state.json");

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

async function readInput() {
  const file = argValue("--file");
  if (file) return readFile(file, "utf-8");

  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf-8");
}

async function main() {
  await mkdir(USER_DIR, { recursive: true });
  const input = await readInput();
  const payload = JSON.parse(input);
  const tweets = payload.tweets || [];

  const state = existsSync(STATE_PATH)
    ? JSON.parse(await readFile(STATE_PATH, "utf-8"))
    : { seenTweets: {} };
  if (!state.seenTweets) state.seenTweets = {};

  const now = new Date().toISOString();
  for (const tweet of tweets) {
    if (tweet.id) state.seenTweets[tweet.id] = now;
  }

  const cutoff = Date.now() - 90 * 24 * 60 * 60 * 1000;
  for (const [id, seenAt] of Object.entries(state.seenTweets)) {
    if (new Date(seenAt).getTime() < cutoff) delete state.seenTweets[id];
  }

  await writeFile(STATE_PATH, JSON.stringify(state, null, 2) + "\n");
  console.log(JSON.stringify({ status: "ok", marked: tweets.length, statePath: STATE_PATH }, null, 2));
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", message: err.message }, null, 2));
  process.exit(1);
});
