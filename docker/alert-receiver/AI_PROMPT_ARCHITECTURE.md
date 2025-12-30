# AI 분석 프롬프트 아키텍처 및 원리

## 개요

이 문서는 `incident_ai.py`에서 구현된 AI 분석 프롬프트의 원리와 구현 방식을 설명합니다.

## 1. 핵심 기술 스택

### 1.1 LangChain 프레임워크
- **역할**: LLM(Large Language Model)과의 상호작용을 추상화하는 프레임워크
- **주요 컴포넌트**:
  - `PromptTemplate`: 구조화된 프롬프트 템플릿 생성
  - `LLMChain`: 프롬프트와 LLM을 연결하는 체인
  - `Ollama`: 로컬 LLM 실행 환경

### 1.2 Ollama
- **역할**: 로컬에서 LLM을 실행하는 도구
- **모델**: `mistral` (현재 설정)
- **장점**: 
  - 데이터 프라이버시 보장 (로컬 실행)
  - API 비용 없음
  - 네트워크 의존성 최소화

## 2. 프롬프트 엔지니어링 원리

### 2.1 구조화된 프롬프트 템플릿 (Structured Prompt Template)

```python
prompt_template = PromptTemplate(
    input_variables=["incident_context", "alert_summary"],
    template="""..."""
)
```

**원리**:
- **템플릿 변수**: `{incident_context}`, `{alert_summary}` 같은 플레이스홀더 사용
- **동적 데이터 주입**: 런타임에 실제 데이터를 변수에 주입
- **일관성 보장**: 동일한 구조의 프롬프트로 일관된 응답 유도

### 2.2 역할 기반 프롬프팅 (Role-Based Prompting)

```
당신은 Google SRE(Site Reliability Engineering) 원칙을 따르는 DevOps 엔지니어입니다.
```

**원리**:
- **페르소나 설정**: AI에게 특정 역할과 전문성을 부여
- **컨텍스트 제공**: Google SRE 원칙을 따르도록 지시하여 전문적인 분석 유도
- **응답 품질 향상**: 역할 기반 프롬프팅은 LLM의 응답 품질을 크게 향상시킴

### 2.3 Few-Shot Learning / In-Context Learning

프롬프트 내에 예시를 포함하여 원하는 출력 형식을 학습시키는 방식:

```
**응답 형식 (JSON):**
{
    "action_taken_suggestion": "한글로 작성된 구체적인 조치 제안 (2-4줄, 우선순위 포함)",
    "root_cause_analysis": "한글로 작성된 근본 원인 분석 (2-4줄, 알람 패턴과 시스템 상태 종합 분석)",
    "similar_incidents": "한글로 작성된 유사 사건 패턴 설명 (없으면 '없음')"
}
```

**원리**:
- **출력 형식 명시**: JSON 구조를 명확히 제시하여 구조화된 응답 유도
- **예시 제공**: 각 필드의 형식과 내용에 대한 가이드라인 제공
- **제약 조건**: "2-4줄", "우선순위 포함" 등 구체적인 요구사항 명시

## 3. 프롬프트 구조 분석

### 3.1 프롬프트 구성 요소

```
1. 역할 정의 (Role Definition)
   ↓
2. 입력 데이터 (Input Data)
   - Incident 정보
   - 관련 알람 정보
   ↓
3. 지침 (Instructions)
   - Google SRE 원칙
   - 언어 요구사항
   - 분석 방법론
   ↓
4. 출력 형식 (Output Format)
   - JSON 구조
   - 필드별 설명
   ↓
5. 제약 조건 (Constraints)
   - 한글 작성 필수
   - 구체성 요구
```

### 3.2 Google SRE 원칙 적용

**Blameless Postmortem 원칙**:
```
Google SRE의 "Blameless Postmortem" 원칙을 따르며, 
객관적이고 사실 기반으로 분석하세요.
```

**원리**:
- **비난 없는 분석**: 사람이나 시스템을 비난하지 않고 사실에 집중
- **객관성**: 감정적 판단 배제, 데이터 기반 분석
- **학습 중심**: 문제 해결보다는 학습과 개선에 초점

## 4. LLMChain 실행 흐름

### 4.1 실행 단계

```python
# 1. LLM 인스턴스 생성
llm = Ollama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, temperature=0.7)

# 2. 프롬프트 템플릿 생성
prompt_template = PromptTemplate(...)

# 3. 체인 생성 (프롬프트 + LLM 연결)
chain = LLMChain(llm=llm, prompt=prompt_template)

# 4. 체인 실행 (변수 주입 및 LLM 호출)
result = chain.run(
    incident_context=incident_context_text,
    alert_summary=alert_summary_text
)
```

### 4.2 Temperature 파라미터

```python
temperature=0.7
```

**원리**:
- **0.0에 가까울수록**: 결정론적, 일관된 응답 (같은 입력 → 같은 출력)
- **1.0에 가까울수록**: 창의적, 다양한 응답
- **0.7**: 균형잡힌 설정 (일관성과 창의성의 조화)

## 5. 구조화된 출력 파싱

### 5.1 JSON 응답 추출

```python
# JSON 부분만 추출 (마크다운 코드 블록 제거)
if "```json" in result_clean:
    result_clean = result_clean.split("```json")[1].split("```")[0].strip()
elif "```" in result_clean:
    result_clean = result_clean.split("```")[1].split("```")[0].strip()

parsed = json.loads(result_clean)
```

**원리**:
- **마크다운 제거**: LLM이 코드 블록 형식으로 응답할 수 있으므로 처리 필요
- **에러 핸들링**: JSON 파싱 실패 시 대체 로직 제공
- **구조화된 데이터**: JSON으로 파싱하여 애플리케이션에서 쉽게 사용

### 5.2 Fallback 메커니즘

```python
except json.JSONDecodeError:
    # JSON 파싱 실패 시 텍스트에서 추출 시도
    return {
        "action_taken_suggestion": result[:500] if result else None,
        "root_cause_analysis": None,
        "similar_incidents": None
    }
```

**원리**:
- **견고성**: LLM 응답이 예상 형식과 다를 때도 처리 가능
- **부분 성공**: 일부 데이터라도 활용 가능하도록 설계

## 6. 프롬프트 엔지니어링 기법

### 6.1 Chain-of-Thought (CoT) 유도

프롬프트에서 단계별 분석을 요구:

```
1. 조치 제안 (action_taken_suggestion):
   - 현재 상황을 해결하기 위한 구체적이고 실행 가능한 단기 조치 방안을 우선순위와 함께 2-3줄로 제안합니다.
```

**원리**:
- **단계별 사고**: 복잡한 문제를 단계별로 분해하여 분석 유도
- **명확한 지시**: 각 단계에서 무엇을 해야 하는지 명확히 제시

### 6.2 제약 조건 명시

```
**중요:** 모든 필드의 값은 반드시 한글로 작성하세요. 영어나 다른 언어를 사용하지 마세요.
```

**원리**:
- **명시적 제약**: 원하는 출력 형식을 명확히 지정
- **반복 강조**: 중요한 요구사항은 여러 번 언급하여 준수 확률 증가

### 6.3 컨텍스트 제공

```
**인시던트 정보:**
{incident_context}

**관련 알람:**
{alert_summary}
```

**원리**:
- **충분한 컨텍스트**: 분석에 필요한 모든 정보를 제공
- **구조화된 입력**: 정보를 카테고리별로 구분하여 이해도 향상

## 7. 데이터 전처리

### 7.1 Incident 정보 포맷팅

```python
incident_context_text = f"""- Incident ID: {incident_info.get("incident_id", "Unknown")}
- Severity: {incident_info.get("severity", "Unknown")}
- Cluster: {incident_info.get("cluster", "Unknown")}
...
"""
```

**원리**:
- **구조화된 텍스트**: 키-값 쌍으로 정보를 명확히 표현
- **기본값 처리**: 누락된 정보에 대한 기본값 제공

### 7.2 알람 정보 요약

```python
alert_summary = []
for alert in alerts[:5]:  # 최대 5개만
    alert_summary.append({
        "alertname": alert.get("alertname", "Unknown"),
        "message": alert.get("message", "")[:200],  # 처음 200자만
        "labels": alert.get("labels", {})
    })
```

**원리**:
- **토큰 제한**: LLM의 컨텍스트 윈도우 제한을 고려한 데이터 축소
- **중요 정보 우선**: 최근 알람 5개만 선택하여 핵심 정보 집중
- **메시지 길이 제한**: 긴 메시지는 200자로 제한하여 토큰 절약

## 8. 전체 실행 흐름

```
1. 사용자가 "🤖 AI 분석" 버튼 클릭
   ↓
2. slack_socket.py에서 ai_analysis 액션 감지
   ↓
3. DB에서 Incident 정보 및 관련 알람 조회
   ↓
4. incident_ai.analyze_incident() 호출
   ↓
5. 데이터 전처리 (Incident 정보, 알람 요약)
   ↓
6. PromptTemplate에 데이터 주입
   ↓
7. LLMChain 실행 (Ollama LLM 호출)
   ↓
8. LLM 응답 수신 (JSON 형식)
   ↓
9. JSON 파싱 및 검증
   ↓
10. Slack 스레드에 코멘트로 전송
```

## 9. 주요 설계 원칙

### 9.1 명확성 (Clarity)
- 프롬프트의 각 지시사항이 명확하고 모호하지 않음
- 예시와 형식을 명확히 제시

### 9.2 구조화 (Structure)
- 입력 데이터를 구조화된 형식으로 제공
- 출력도 JSON으로 구조화하여 파싱 용이

### 9.3 견고성 (Robustness)
- JSON 파싱 실패 시 대체 로직 제공
- 예외 상황 처리

### 9.4 효율성 (Efficiency)
- 토큰 사용량 최적화 (알람 5개, 메시지 200자 제한)
- 로컬 LLM 사용으로 비용 절감

## 10. 개선 가능한 영역

### 10.1 Few-Shot Examples 추가
현재는 형식만 제시하지만, 실제 예시를 추가하면 더 나은 결과 기대:

```
예시:
{
    "action_taken_suggestion": "1. 서비스 재시작 (긴급): 영향도 최소화를 위해 즉시 실행. 2. 로그 분석 (중요): 재발 방지를 위한 추가 정보 수집.",
    "root_cause_analysis": "최근 배포된 버전에서 메모리 누수 발생. 특정 조건에서 GC가 정상 작동하지 않아 OOM 발생.",
    "similar_incidents": "지난달에도 유사한 CPU 사용량 급증 알람이 있었음. 당시에는 잘못된 쿼리 실행이 원인이었음."
}
```

### 10.2 RAG (Retrieval-Augmented Generation)
과거 유사한 Incident를 검색하여 컨텍스트로 제공하면 더 정확한 분석 가능

### 10.3 프롬프트 버전 관리
프롬프트를 버전별로 관리하여 A/B 테스트 및 개선 추적 가능

## 11. 참고 자료

- **LangChain 문서**: https://python.langchain.com/
- **Ollama 문서**: https://ollama.ai/
- **Google SRE 책**: "Site Reliability Engineering"
- **프롬프트 엔지니어링 가이드**: "The Art of Prompt Engineering"

