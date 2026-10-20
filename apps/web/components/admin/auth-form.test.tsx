import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { AuthForm } from "./auth-form";

test("가입 화면은 회사 이름·이메일·비밀번호를 받고 로그인 화면은 회사 이름이 없다", () => {
  const signup = renderToStaticMarkup(<AuthForm mode="signup" onSubmit={() => {}} />);
  expect(signup).toContain("관리자 가입");
  for (const label of ["회사 이름", "이메일", "비밀번호"]) expect(signup).toContain(label);

  const login = renderToStaticMarkup(
    <AuthForm mode="login" error="이메일 또는 비밀번호가 맞지 않습니다." onSubmit={() => {}} />,
  );
  expect(login).toContain("관리자 로그인");
  expect(login).not.toContain("회사 이름");
  expect(login).toContain("이메일 또는 비밀번호가 맞지 않습니다.");
});
