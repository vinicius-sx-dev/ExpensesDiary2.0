"""The LLM can choose tone, but cannot alter the mathematical result."""

import json
import re

import httpx

from app.config import settings


def anonymous_payload(pattern, result):
    # Construct an allowlist; never remove keys from a rich user/price/goal object.
    return {
        "category": pattern["strategy"],
        "context": "optional_spending_alternative",
        "per_occurrence_cents": result["per_occurrence_cents"],
        "monthly_savings_cents": result["monthly_savings_cents"],
        "days_earlier": result["days_earlier"],
    }


def humanize(pattern, result):
    fallback = "Uma pequena mudança pode ajudar sua meta. Veja os cálculos e escolha o que cabe na sua rotina."
    if not settings.groq_api_key or result.get("status") != "ready":
        return fallback
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            r = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + settings.groq_api_key},
                json={
                    "model": settings.groq_model,
                    "temperature": 0.2,
                    "max_completion_tokens": 200,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Escreva uma frase curta em português, empática e sem julgamento, convidando a considerar a alternativa. Não dê conselhos adicionais, não prometa resultados e não escreva números, preços, datas ou cálculos: o aplicativo mostra os cálculos separadamente. Retorne apenas JSON com a chave message.",
                        },
                        {"role": "user", "content": json.dumps(anonymous_payload(pattern, result))},
                    ],
                },
            )
            r.raise_for_status()
            if len(r.content) > 16384:
                return fallback
            content = json.loads(r.json()["choices"][0]["message"]["content"])
            message = content["message"]
            if (
                set(content) != {"message"}
                or not isinstance(message, str)
                or not 10 <= len(message) <= 300
                or re.search(r"[\d<>]|https?://|R\$", message)
            ):
                return fallback
            return message
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        return fallback
