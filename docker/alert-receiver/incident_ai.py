"""
Incident AI 분석 모듈
LangChain과 Ollama를 사용하여 로컬 AI로 Incident 분석 및 조치 제안
"""
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from langchain_community.llms import Ollama
    from langchain.prompts import PromptTemplate
    from langchain.chains import LLMChain
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("⚠️  langchain 또는 langchain-community가 설치되지 않았습니다.")

# Ollama 설정
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")  # mistral 모델 사용


def get_ai_llm():
    """
    Ollama LLM 인스턴스 생성
    """
    if not LANGCHAIN_AVAILABLE:
        return None
    
    try:
        llm = Ollama(
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            temperature=0.7
        )
        return llm
    except Exception as e:
        print(f"⚠️  Ollama 연결 실패: {e}")
        return None


def analyze_incident(incident_info: Dict[str, Any], alerts: list) -> Dict[str, str]:
    """
    Incident를 AI로 분석하여 조치 제안 및 근본 원인 분석
    
    Args:
        incident_info: Incident 정보 (incident_id, status, severity, cluster, namespace, phase, service 등)
        alerts: 관련 알람 리스트 (alertname, message, labels 등)
    
    Returns:
        {
            "action_taken_suggestion": "제안된 조치 내용",
            "root_cause_analysis": "근본 원인 분석",
            "similar_incidents": "유사한 사건 패턴"
        }
    """
    if not LANGCHAIN_AVAILABLE:
        return {
            "action_taken_suggestion": None,
            "root_cause_analysis": None,
            "similar_incidents": None
        }
    
    llm = get_ai_llm()
    if not llm:
        return {
            "action_taken_suggestion": None,
            "root_cause_analysis": None,
            "similar_incidents": None
        }
    
    # 알람 정보 요약
    alert_summary = []
    for alert in alerts[:5]:  # 최대 5개만
        alert_summary.append({
            "alertname": alert.get("alertname", "Unknown"),
            "message": alert.get("message", "")[:200],  # 처음 200자만
            "labels": alert.get("labels", {})
        })
    
    # 프롬프트 템플릿 (Google SRE 스타일 기반)
    prompt_template = PromptTemplate(
        input_variables=["incident_context", "alert_summary"],
        template="""당신은 Google SRE(Site Reliability Engineering) 원칙을 따르는 DevOps 엔지니어입니다. 
다음 알람 정보를 분석하여 명확하고 실행 가능한 인시던트 코멘트를 작성해주세요.

**인시던트 정보:**
{incident_context}

**관련 알람:**
{alert_summary}

**지침:**
1. Google SRE의 "Blameless Postmortem" 원칙을 따르며, 객관적이고 사실 기반으로 분석하세요.
2. 모든 응답은 반드시 한글로 작성하세요.
3. 조치 제안은 구체적이고 실행 가능해야 하며, 우선순위를 명시하세요.
4. 근본 원인 분석은 알람 패턴, 시스템 상태, 리소스 사용량 등을 종합적으로 고려하세요.
5. 유사 사건이 있다면 패턴을 간단히 설명하고, 없다면 "없음"으로 표시하세요.

**응답 형식 (JSON):**
{{
    "action_taken_suggestion": "한글로 작성된 구체적인 조치 제안 (2-4줄, 우선순위 포함)",
    "root_cause_analysis": "한글로 작성된 근본 원인 분석 (2-4줄, 알람 패턴과 시스템 상태 종합 분석)",
    "similar_incidents": "한글로 작성된 유사 사건 패턴 설명 (없으면 '없음')"
}}

**중요:** 모든 필드의 값은 반드시 한글로 작성하세요. 영어나 다른 언어를 사용하지 마세요.
"""
    )
    
    try:
        # Incident 정보 포맷팅
        start_time_str = ""
        if incident_info.get("start_time"):
            if isinstance(incident_info.get("start_time"), datetime):
                start_time_str = incident_info.get("start_time").strftime("%Y-%m-%d %H:%M:%S")
            else:
                start_time_str = str(incident_info.get("start_time", ""))
        
        incident_context_text = f"""- Incident ID: {incident_info.get("incident_id", "Unknown")}
- Severity: {incident_info.get("severity", "Unknown")}
- Cluster: {incident_info.get("cluster", "Unknown")}
- Namespace: {incident_info.get("namespace", "Unknown")}
- Phase: {incident_info.get("phase", "Unknown")}
- Service: {incident_info.get("service", "Unknown")}
- Status: {incident_info.get("status", "Unknown")}
- 발생 시각: {start_time_str}
- 알람 개수: {incident_info.get("alert_count", 0)}"""
        
        alert_summary_text = json.dumps(alert_summary, ensure_ascii=False, indent=2)
        
        # 프롬프트 실행
        print(f"🤖 LangChain 프롬프트 실행 시작...")
        chain = LLMChain(llm=llm, prompt=prompt_template)
        result = chain.run(
            incident_context=incident_context_text,
            alert_summary=alert_summary_text
        )
        print(f"🤖 LangChain 프롬프트 실행 완료, 결과 길이: {len(result) if result else 0}")
        
        # JSON 파싱 시도
        try:
            # JSON 부분만 추출 (마크다운 코드 블록 제거)
            result_clean = result.strip()
            if "```json" in result_clean:
                result_clean = result_clean.split("```json")[1].split("```")[0].strip()
            elif "```" in result_clean:
                result_clean = result_clean.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(result_clean)
            return {
                "action_taken_suggestion": parsed.get("action_taken_suggestion"),
                "root_cause_analysis": parsed.get("root_cause_analysis"),
                "similar_incidents": parsed.get("similar_incidents")
            }
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트에서 추출 시도
            print(f"⚠️  AI 응답 JSON 파싱 실패, 원본: {result[:200]}")
            return {
                "action_taken_suggestion": result[:500] if result else None,
                "root_cause_analysis": None,
                "similar_incidents": None
            }
    
    except Exception as e:
        print(f"❌ AI 분석 실패: {e}")
        import traceback
        traceback.print_exc()
        return {
            "action_taken_suggestion": None,
            "root_cause_analysis": None,
            "similar_incidents": None
        }


def get_incident_analysis_for_modal(incident_id: str, conn) -> Dict[str, str]:
    """
    Resolve 모달을 위한 Incident 분석 결과 반환
    
    Args:
        incident_id: Incident ID
        conn: DB 연결
    
    Returns:
        {
            "action_taken_suggestion": "제안된 조치 내용",
            "root_cause_analysis": "근본 원인 분석"
        }
    """
    try:
        # Incident 정보 조회
        from incident_service import get_incident_info
        incident_info = get_incident_info(conn, incident_id)
        if not incident_info:
            return {"action_taken_suggestion": None, "root_cause_analysis": None}
        
        # 관련 알람 조회
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT alertname, message, labels, annotations
                FROM grafana_alerts
                WHERE incident_id = %s
                ORDER BY received_at DESC
                LIMIT 10
            """, (incident_id,))
            alerts = cursor.fetchall()
        
        # 알람 데이터 포맷팅
        formatted_alerts = []
        for alert in alerts:
            labels = alert.get("labels") or {}
            if isinstance(labels, str):
                labels = json.loads(labels)
            
            formatted_alerts.append({
                "alertname": alert.get("alertname", ""),
                "message": alert.get("message", ""),
                "labels": labels,
                "annotations": alert.get("annotations", {})
            })
        
        # AI 분석
        analysis = analyze_incident(incident_info, formatted_alerts)
        
        return {
            "action_taken_suggestion": analysis.get("action_taken_suggestion"),
            "root_cause_analysis": analysis.get("root_cause_analysis")
        }
    
    except Exception as e:
        print(f"❌ Incident 분석 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        return {"action_taken_suggestion": None, "root_cause_analysis": None}

