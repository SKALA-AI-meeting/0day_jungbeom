// 완료 기준(web-kit): Avatar 원형 크롭·이니셜 대체·자리 색, 기존 props 호환, LevelChip·ConfidenceTag 표기.
import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { Avatar, AvatarGroup, visibleSrc } from "./avatar";
import { ConfidenceTag } from "./confidence-tag";
import { LevelChip } from "./level-chip";
import { Tabs } from "./tabs";

test("Avatar: 이미지가 없으면 이름 첫 글자 이니셜을 자리 색으로 그린다", () => {
  const html = renderToStaticMarkup(<Avatar name="민준" seat="p1" />);
  expect(html).toContain('aria-label="민준"');
  expect(html).toContain(">민<");
  expect(html).toContain("bg-seat-p1");
  expect(html).not.toContain("<img");
});

test("Avatar: 이미지는 원형 크롭·cover로 겹치고, 실패 대비 이니셜이 아래에 깔린다", () => {
  const html = renderToStaticMarkup(
    <Avatar name="서연" seat="p2" src="/mock-avatars/avatar-02.png" size={36} />,
  );
  expect(html).toContain('src="/mock-avatars/avatar-02.png"');
  expect(html).toContain("object-cover");
  expect(html).toContain("rounded-full");
  expect(html).toContain("size-9");
  expect(html).toContain(">서<");
  // 로드에 실패한 src는 다시 그리지 않는다 → 이니셜만 남음
  expect(visibleSrc("/a.png", "/a.png")).toBeNull();
  expect(visibleSrc("/b.png", "/a.png")).toBe("/b.png");
  expect(visibleSrc("", undefined)).toBeNull();
});

test("Avatar: 기존 label·tone props와 AvatarGroup이 그대로 동작한다", () => {
  const html = renderToStaticMarkup(
    <>
      <Avatar label="서" tone="manager" size={36} online name="한서윤" />
      <AvatarGroup
        people={[
          { label: "나", tone: "candidate", name: "나" },
          { name: "지호", seat: "p3" },
        ]}
      />
    </>,
  );
  expect(html).toContain("bg-person-manager");
  expect(html).toContain('aria-label="한서윤"');
  expect(html).toContain("bg-person-candidate");
  expect(html).toContain("bg-seat-p3");
  expect(html).toContain('title="지호"');
});

test("LevelChip: 수준·목록용·기록 없음 사유·담당자 조정을 글자로 표기한다", () => {
  expect(renderToStaticMarkup(<LevelChip level={3} />)).toContain("수준 3 (1~5)");
  expect(renderToStaticMarkup(<LevelChip level={3} label="설득" />)).toContain("설득 3");
  expect(
    renderToStaticMarkup(
      <LevelChip level={null} reason="핵심 장면에 지원자 메시지가 없었습니다" />,
    ),
  ).toContain("핵심 장면에 지원자 메시지가 없었습니다");
  expect(renderToStaticMarkup(<LevelChip level={4} adjusted />)).toContain("담당자 조정됨");
  expect(
    renderToStaticMarkup(<LevelChip level={null} label="협업" reason="해당 장면이 없었습니다" />),
  ).toContain("협업 · 기록 없음");
});

test("LevelChip: 타입이 수준 1~5만 받고, 기록 없음이면 사유를 요구한다", () => {
  // @ts-expect-error 수준은 1~5만
  void (<LevelChip level={6} />);
  // @ts-expect-error 기록 없음(null)에는 사유가 필요
  void (<LevelChip level={null} />);
  // @ts-expect-error 수준이 있으면 사유를 받지 않는다
  void (<LevelChip level={2} reason="불필요" />);
  expect(true).toBe(true);
});

test("ConfidenceTag: 확신도를 아이콘+글자로, 낮음은 원문 확인 권장 문구를 붙인다", () => {
  expect(renderToStaticMarkup(<ConfidenceTag confidence="high" />)).toContain("확신도 높음");
  const medium = renderToStaticMarkup(<ConfidenceTag confidence="medium" />);
  expect(medium).toContain("확신도 보통");
  expect(medium).not.toContain("원문 확인 권장");
  const low = renderToStaticMarkup(<ConfidenceTag confidence="low" />);
  expect(low).toContain("근거 약함, 원문 확인 권장");
  expect(low).toContain("<svg");
});

test("Tabs: segmented 모양에서도 같은 items props로 탭과 배지를 그린다", () => {
  const html = renderToStaticMarkup(
    <Tabs
      variant="segmented"
      items={[
        { value: "consensus", label: "합의", content: "a" },
        { value: "materials", label: "자료", count: 2, content: "b" },
      ]}
    />,
  );
  expect(html).toContain("합의");
  expect(html).toContain("자료");
  expect(html).toContain(">2<");
});
