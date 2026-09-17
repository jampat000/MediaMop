#!/usr/bin/env node
/**
 * Clear local auth tables so first-run bootstrap (/setup) works again.
 *
 * Use when you forgot the admin password of a development database. Uses the SQLite file the server
 * would use: WEIR_DB_PATH (relative paths under WEIR_HOME), else <WEIR_HOME>/data/weir.sqlite3, where
 * WEIR_HOME defaults the same way the server's does. scripts/dev-reset-auth.ps1 loads the repository
 * .env first. Refuses to run unless WEIR_ENV is `development`, unless you pass --force.
 *
 *   node scripts/dev-reset-auth.mjs --list     print accounts, change nothing
 *   node scripts/dev-reset-auth.mjs --yes      delete every session and user
 *
 * Stop the server first, or restart it afterwards: signed-in browsers keep their cookie until then.
 */
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const args = new Set(process.argv.slice(2));

function weirHome() {
  const explicit = (process.env.WEIR_HOME || "").trim();
  if (explicit) return path.resolve(explicit.replace(/^~(?=$|[\\/])/, os.homedir()));
  if (process.platform === "win32") {
    return path.join(process.env.PROGRAMDATA || "C:\\ProgramData", "Weir");
  }
  const xdg = (process.env.XDG_DATA_HOME || "").trim();
  return xdg ? path.join(xdg, "weir") : path.join(os.homedir(), ".local", "share", "weir");
}

function databasePath(home) {
  const configured = (process.env.WEIR_DB_PATH || "").trim();
  if (!configured) return path.join(home, "data", "weir.sqlite3");
  return path.isAbsolute(configured) ? configured : path.join(home, configured);
}

const env = (process.env.WEIR_ENV || "development").trim().toLowerCase();
if (env !== "development" && !args.has("--force")) {
  console.error(
    `FAIL: WEIR_ENV is '${process.env.WEIR_ENV}', not development. ` +
      "Use --force if you really mean to wipe auth on this database.",
  );
  process.exit(2);
}

const dbPath = databasePath(weirHome());
if (!existsSync(dbPath)) {
  console.error(`FAIL: no database at ${dbPath}. Start the server once (it creates the database) or set WEIR_HOME.`);
  process.exit(2);
}

const db = new DatabaseSync(dbPath);
try {
  if (args.has("--list")) {
    const users = db.prepare("SELECT username, role, is_active FROM users ORDER BY username").all();
    if (users.length === 0) {
      console.log("No users in database — open /setup to create the first admin.");
    } else {
      console.log("Users in database:");
      for (const row of users) {
        console.log(`  - '${row.username}'  role='${row.role}'  active=${Boolean(row.is_active)}`);
      }
      console.log("\nTo start over, run:  node scripts/dev-reset-auth.mjs --yes");
    }
    process.exit(0);
  }
  if (!args.has("--yes")) {
    console.error(
      "This will DELETE all rows in user_sessions and users (you can use /setup again afterward).\n" +
        "Re-run with --yes to confirm, or --list to see accounts.",
    );
    process.exit(1);
  }
  db.exec("BEGIN");
  db.exec("DELETE FROM user_sessions");
  db.exec("DELETE FROM users");
  db.exec("COMMIT");
  console.log(`OK: Cleared sessions and users in ${dbPath}.`);
  console.log("Open /setup on your Weir URL to create the admin account again.");
} finally {
  db.close();
}
