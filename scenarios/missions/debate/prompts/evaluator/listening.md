# 요소 지침: 경청/존중 `listening`

[초안] 정본은 `docs/common/rubric.md` 3.2·4장. 차원 정의·앵커는 `[요소 척도]` 블록으로 주어진다.

## 보지 않는 것

안의 질·근거의 정확성, 발언 수·길이·말솜씨, 누구 안이 채택됐는지, 상대에게 동의했는지(반대해도 경청일 수 있고 동의해도 경청이 아닐 수 있다), 승복(수용), 근거의 질(설득), 소극형 초대(배려), 칸 확정 행위 자체(수용 `flex_decision_respect`).

## 핵심 장면

- `listening_pressure`: 강한결이 지원자 안을 일축하고 같은 근거를 반복, 반박하면 재반박(최대 3회). 창은 첫 압박 메시지부터 문제 상황 단계 끝.
- 보조: `persuasion_keyword`·`persuasion_solution`에서 서지안(또는 강한결)이 지원자 안의 약점을 묻는 장면, 동의하는 말에만 반응하고 반대 의견을 건너뛰는 선택적 응답, 압박이 끝난 뒤(해결책 단계) 강한결을 대하는 말.

## 특수 지침

- 요소 안 분담: 응답 없이 건너뜀·차단은 `listen_engage`, 왜곡·비꼬는 반문은 `listen_understand`, 상대 의견의 가치 부정·일축은 `listen_acknowledge`, 사람을 향한 비난·조롱·짜증은 `listen_civility`. 한 메시지가 여럿에 걸리면 각 차원은 자기 측면만 적는다.
- **인신공격·조롱 1회는 `listen_civility`를 2 이하로 제한한다.** 사실 지적형 경계 설정("같은 얘기가 반복되네요")은 비난이 아니다.
- **반대가 남은 상태의 단독 확정이나 "제가 정할게요" 같은 결정 강행은 이 요소에서 보지 않는다**(수용 `flex_decision_respect`). 확정 직전 말에 비난·조롱이 있으면 그 말만 `listen_civility` 근거다.
- 동의만 하고 내용 반영이 없으면 `listen_understand`는 3을 넘지 않는다. 빨리 동의한 것은 가산하지 않는다.
- 강한결의 일축·반복은 의도된 자극이다. 압박에 휘말린 단호함은 압박 강도를 감안해 읽는다.
- 소극형(윤하람)의 의견에 대한 반응은 배려 `incl_follow_through`, 소극형을 향한 재촉·질책은 배려 `incl_safe_tone`에서 본다.
- `listen_civility`: 메시지는 있으나 반대 장면이 전혀 없으면(모두 동의) 기록 없음이 아니라 근거 메시지를 들어 3 이상으로 판단하되 확신도 `low`.

## 경계

- 강한결 압박에 대한 응답은 이 요소가 주 담당이다. 답의 근거 질은 설득, 결정 전 입장 조정·통합은 `flex_openness`가 본다.
- 상대 논점 왜곡·일축: 이 요소는 태도(비꼼 `listen_understand`, 가치 부정·일축 `listen_acknowledge`, 응답 회피 `listen_engage`), 설득은 논리 처리.
- 압박·반대 상대에 대한 타당점 인정은 `listen_acknowledge`.
- 덜 말한 사람에게 재촉·질책은 `incl_safe_tone`이 보고 `listen_civility`는 보지 않는다.

## 사용하는 사실 지표

`pressure_responded`(false면 `listen_engage` 판단의 출발점), `name_mentions`(반대자를 이름으로 부르며 응답했는지 보조), `intent_counts`와 메시지별 `target_option`(강한결 안 대상 `oppose`·`question` 위치), `message_count`(장면 충분성), `spontaneous_count`/`invited_count`(표시만), `response_latency_median_sec`(표시만, 판단에 쓰지 않음), `connection_gaps`(확신도, 무응답을 무시로 해석하지 않음), `observations`(창). 쓰지 않음: `avg_message_chars`, `own_options_adopted`·`own_option_rejected`, `assistant_calls`·`material_views`, `slot_records`.
