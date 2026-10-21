# playtest 드라이버

블라인드 페르소나 에이전트가 Bash만으로 같은 브라우저(Playwright chromium)를 여러 호출에 걸쳐 조작한다.

1. 시작(설치된 chromium 1243에 맞춰 1.63.0 고정): `uv run --with playwright==1.63.0 python tests/playtest/driver.py start --url http://localhost:3100/ --out <dir> --name <name>` (포트 기본 9400, 환경변수 `PLAYTEST_PORT`나 `--port`로 바꾼다. 포트가 다르면 이후 명령에도 같은 `--port`를 준다)
2. 보기: `python3 tests/playtest/driver.py shot <이름>`은 PNG 경로를 출력하니 Read 도구로 열어 본다. `text`는 보이는 본문 텍스트
3. 조작: `click "<보이는 텍스트>"`, `fill "<라벨 또는 placeholder>" "<값>"`, `type "<값>"`, `press Enter`, `goto <url>`, `wait <초>`(최대 10). 텍스트로 안 잡히면 `css=<selector>`
4. 끝: `stop`이 영상을 `<out>/<name>.webm`으로 저장하고 서버를 종료한다
5. 대화상자(alert/confirm)는 자동으로 닫히고 `<out>/server.log`에 남는다

## 조작 요령

- 조작 뒤에는 `shot`으로 화면을 확인한다. `text`만으로 판단하지 말고 레이아웃도 본다
- `click`이 "못 찾음"이면 출력된 후보 5개를 보고 텍스트를 고치거나 `css=`를 쓴다
- 입력창은 `fill`, 이미 포커스된 곳은 `type` 후 `press Enter`. 응답을 기다릴 땐 `wait 5` 뒤 `shot`
- 사람이 하듯 한 번에 한 동작만 하고, 막히면 막힌 지점을 있는 그대로 기록한다
