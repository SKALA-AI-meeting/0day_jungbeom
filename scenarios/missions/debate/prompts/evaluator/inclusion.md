# 요소 지침: 배려/포용 `inclusion`

[초안] 정본은 `docs/common/rubric.md` 3.3·4장. 차원 정의·앵커는 `[요소 척도]` 블록으로 주어진다.

## 보지 않는 것

지원자 본인의 발언량·말솜씨, 안의 질과 근거의 정확성, 소극형의 안(S3) 채택 여부, 지원자 본인의 성격, 행동이 없는 친절한 말투, 강한결 압박에 대한 대응 품질(경청), 반대가 남은 상태의 단독 확정 행위 자체(수용).

## 핵심 장면

- `inclusion_silence`: 해결책 단계 시작 후 `L/30`에 윤하람이 "저… 하나 생각한 게 있긴 한데… 아니에요, 먼저 얘기하세요."라고 말하고, 이름이 불리거나 전체 질문이 올 때까지 침묵한다. 초대받으면 S3를 자료 근거와 함께 말하고, 무시당하면 다시 말하지 않는다. 창은 머뭇거림 메시지부터 해결책 단계 끝(칸 확정 기록 포함).
- 설계상 보장: 창 안에서 다른 페르소나는 윤하람에게 발언 기회를 주거나 이름을 부르지 않는다. 창 안의 초대는 모두 지원자 몫이다.
- 보조: 키워드·문제 상황 단계에서 윤하람이나 덜 말한 동료에게 묻기, 칸 확정 전 미표명자 확인, 강한결이 대화를 독점할 때 다른 사람에게 발언 돌리기.
- 장면 아님: 침묵 초대(AI 동료가 지원자에게 묻는 것)는 지원자가 받은 배려라 근거가 아니다.

## 특수 지침

- `incl_notice_invite`·`incl_follow_through`는 `inclusion_silence` 창이 핵심 장면, `incl_shared_decision`·`incl_safe_tone`은 세션 전체가 핵심 장면이다. 질책·발언 막기는 1회로도 해당 수준의 근거가 된다.
- 이중 감점 금지: 초대 부재는 `incl_notice_invite`에만, 그 결과인 의견 부재는 `incl_follow_through` 기록 없음.
- 이름이 들어간 메시지라도 동의 요구("하람님 맞죠?")·유도형은 초대로 보지 않는다(`incl_notice_invite` ≤ 2, `incl_safe_tone` ≤ 2).
- 소극형의 S3를 듣고 근거를 들어 반대하거나 채택하지 않아도 내용을 검토했다면 `incl_follow_through` 4 이상이 가능하다.
- `incl_shared_decision`은 **미표명자를 확인했는지**만 본다. 반대 의견이 남은 상태에서 확정한 행위 자체는 수용 `flex_decision_respect`가 본다.
- 지원자가 침묵 초대를 받은 뒤 한 발언 안에서 소극형을 초대했다면 그대로 인정한다.
- 카드 창 시작 전(키워드·문제 상황)의 소극형 초대도 보조 장면으로 인정한다.

## 경계

- 반대가 남은 단독 확정: 주 담당은 `flex_decision_respect`. `incl_shared_decision`은 의견을 내지 않은 사람을 확인했는지만 본다.
- 소극형 머뭇거림 뒤 초대: 주 담당 `incl_notice_invite`, `incl_safe_tone`은 초대 말의 부담·유도 여부.
- 소극형 의견에 대한 반응: 주 담당 `incl_follow_through`. 그 안을 다시 말할 때 출처는 `hon_source_in_talk`.
- 덜 말한 사람에게 재촉·질책: `incl_safe_tone`.
- 결정 전 미표명자 확인: `incl_shared_decision`(반대자 확인은 `flex_decision_respect`).
- 지원자가 받은 침묵 초대는 어느 차원의 근거도 아니다.

## 사용하는 사실 지표

`invite_latency_sec`(알아차림 보조, 단독으로 수준 결정 금지), `quiet_spoke`(`incl_follow_through` 적용 여부, 초대가 발언으로 이어졌는지), `name_mentions`(호명 분포), `slot_records`(확정 시점 지지 현황 스냅샷으로 미표명자 확인), `message_count`·`first_message_sec`(활동·확신도), `spontaneous_count`/`invited_count`, `silence_invites_received`(받은 초대를 배려 행동으로 잘못 세지 않기), `intent_counts`(질문 의도 보조), `connection_gaps`, `observations`(머뭇거림 시각·창).
