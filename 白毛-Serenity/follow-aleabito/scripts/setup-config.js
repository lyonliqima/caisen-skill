#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const USER_DIR = join(homedir(), ".follow-aleabito");
const CONFIG_PATH = join(USER_DIR, "config.json");
const ENV_EXAMPLE_PATH = join(USER_DIR, ".env.example");

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

async function readConfig() {
  if (!existsSync(CONFIG_PATH)) return {};
  return JSON.parse(await readFile(CONFIG_PATH, "utf-8"));
}

async function main() {
  await mkdir(USER_DIR, { recursive: true });

  const existing = await readConfig();
  const recipient = argValue("--recipient") ?? existing.delivery?.recipient ?? "";
  const timezone =
    argValue("--timezone") ?? existing.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "America/Los_Angeles";
  const deliveryTime = argValue("--time") ?? existing.deliveryTime ?? "08:00";
  const notifyWhenEmpty = hasFlag("--no-empty-notify")
    ? false
    : existing.notifyWhenEmpty ?? true;

  const config = {
    handle: "aleabitoreddit",
    displayName: "Serenity",
    language: "zh",
    timezone,
    frequency: "daily",
    deliveryTime,
    lookbackHours: Number(argValue("--lookback-hours") ?? existing.lookbackHours ?? 24),
    maxTweets: Number(argValue("--max-tweets") ?? existing.maxTweets ?? 5),
    dedupe: existing.dedupe ?? true,
    chromeFallback: existing.chromeFallback ?? true,
    notifyWhenEmpty,
    delivery: {
      method: "imessage",
      recipient,
    },
  };

  await writeFile(CONFIG_PATH, JSON.stringify(config, null, 2) + "\n");

  if (!existsSync(ENV_EXAMPLE_PATH)) {
    await writeFile(
      ENV_EXAMPLE_PATH,
      [
        "# Optional but recommended: official X API bearer token for latest tweets.",
        "# Without it, the skill falls back to X's public syndication page, which may miss or truncate posts.",
        "X_BEARER_TOKEN=",
        "",
      ].join("\n"),
    );
  }

  console.log(JSON.stringify({ status: "ok", configPath: CONFIG_PATH, envExamplePath: ENV_EXAMPLE_PATH }, null, 2));
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", message: err.message }, null, 2));
  process.exit(1);
});
