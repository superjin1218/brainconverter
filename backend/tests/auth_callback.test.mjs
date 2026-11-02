import assert from "node:assert/strict";
import test from "node:test";
import {clearLegacyAuthLink} from "../app/static/js/auth-callback.js";

test("legacy email links clear secrets without a verification request or session import", async () => {
  for (const [search, hash] of [
    ["", "#access_token=secret&refresh_token=secret&type=signup"],
    ["?access_token=secret", ""], ["?code=secret", ""], ["?token_hash=secret", ""],
    ["", "#access_token=secret&type=recovery"], ["?error_description=secret", ""],
    ["", "#error=secret"],
  ]) {
    let cleared = false;
    const message = await clearLegacyAuthLink(
      {pathname: "/auth/callback", search, hash},
      {replaceState: (data, title, url) => { cleared = true; assert.equal(url, "/auth/callback"); }},
    );
    assert.equal(cleared, true);
    assert.match(message, /이메일과 비밀번호로 로그인/);
    assert.equal(message.includes("secret"), false);
  }
});

test("normal visits preserve the URL", async () => {
  assert.equal(await clearLegacyAuthLink(
    {pathname: "/", search: "?view=welcome", hash: ""},
    {replaceState: () => assert.fail("normal visit must preserve URL")},
  ), null);
});
