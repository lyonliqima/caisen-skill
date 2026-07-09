#!/usr/bin/env node

import { readFile } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { spawn } from "child_process";

const USER_DIR = join(homedir(), ".follow-aleabito");
const CONFIG_PATH = join(USER_DIR, "config.json");

function argValue(name) {
  const idx = process.argv.indexOf(name);
  return idx === -1 ? null : process.argv[idx + 1] || null;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

async function readInput() {
  const message = argValue("--message");
  if (message) return message;

  const file = argValue("--file");
  if (file) return readFile(file, "utf-8");

  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf-8");
}

async function readConfig() {
  if (!existsSync(CONFIG_PATH)) return {};
  return JSON.parse(await readFile(CONFIG_PATH, "utf-8"));
}

function splitMessage(text, maxLen = 3500) {
  const chunks = [];
  let remaining = text.trim();
  while (remaining.length > maxLen) {
    let splitAt = remaining.lastIndexOf("\n", maxLen);
    if (splitAt < maxLen * 0.5) splitAt = maxLen;
    chunks.push(remaining.slice(0, splitAt).trim());
    remaining = remaining.slice(splitAt).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

function runOsaScript(recipient, message) {
  const script = `
on run argv
  set targetAddress to item 1 of argv
  set messageText to item 2 of argv
  tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy targetAddress of targetService
    send messageText to targetBuddy
  end tell
end run
`;

  return new Promise((resolve, reject) => {
    const child = spawn("osascript", ["-e", script, recipient, message], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("close", (code) => {
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(stderr.trim() || `osascript exited with code ${code}`));
    });
  });
}

async function main() {
  const config = await readConfig();
  const recipient = argValue("--to") || config.delivery?.recipient;
  const text = await readInput();

  if (!recipient) {
    throw new Error(
      `Missing iMessage recipient. Run: node ${join(
        homedir(),
        ".codex",
        "skills",
        "follow-aleabito",
        "scripts",
        "setup-config.js",
      )} --recipient "<phone-or-apple-id>"`,
    );
  }
  if (!text.trim()) throw new Error("Refusing to send an empty message");

  const chunks = splitMessage(text);
  if (hasFlag("--dry-run")) {
    console.log(JSON.stringify({ status: "dry-run", recipient, chunks: chunks.length }, null, 2));
    return;
  }

  for (const chunk of chunks) {
    await runOsaScript(recipient, chunk);
    if (chunks.length > 1) await new Promise((resolve) => setTimeout(resolve, 700));
  }

  console.log(JSON.stringify({ status: "ok", method: "imessage", recipient, chunks: chunks.length }, null, 2));
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", message: err.message }, null, 2));
  process.exit(1);
});
