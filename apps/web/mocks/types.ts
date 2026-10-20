// mock 경로 표의 한 줄. admin.ts·office.ts가 이 형식으로 ROUTES를 내보낸다.
export type MockHandler = (params: Record<string, string>, body: unknown) => unknown;

/** [메서드, 경로 패턴(":id" 같은 자리 표시), 응답 함수] */
export type MockRoute = [method: string, pattern: string, handler: MockHandler];
