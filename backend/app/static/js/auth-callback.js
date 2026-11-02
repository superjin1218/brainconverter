// Old email links must never import URL tokens into a browser session.
export function clearLegacyAuthLink(location, history) {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const query = new URLSearchParams(location.search);
  const relevant = ["access_token", "refresh_token", "error", "error_code", "error_description", "code", "token_hash"];
  if (!relevant.some(key => fragment.has(key) || query.has(key))) return Promise.resolve(null);
  history.replaceState(null, "", location.pathname);
  return Promise.resolve("이메일 인증 절차가 종료되었습니다. 이메일과 비밀번호로 로그인하세요.");
}
