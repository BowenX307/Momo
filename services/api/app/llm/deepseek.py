"""DeepSeek provider implementation."""

import httpx

from app.core.config import settings


class DeepSeekProvider:
    async def complete(self, scene: str, user_text: str) -> str:
        prompt = (
            "你是 MOMO，一个中文情绪陪伴助手。"
            "请保持温柔、清晰、不过度建议，避免医疗诊断措辞。"
        )
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"scene={scene}\n用户输入：{user_text}"},
            ],
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]
