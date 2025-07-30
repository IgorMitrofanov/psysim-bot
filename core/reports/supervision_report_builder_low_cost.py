from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Persona
import json
from config import logger
from core.persones.llm_engine import call_llm_for_meta_ai

SUPERVISION_REPORT_TEMP = 0.9

class SupervisionReportBuilder:
    def __init__(self, persona_loader, session_history: List[Dict]):
        self.session_history = session_history
        self.persona_loader = persona_loader
        self._total_tokens = 0

    async def generate_report(self, persona_name: str) -> Tuple[str, int]:
        """Generate complete supervision report in HTML with single LLM call"""
        try:
            persona_data = await self._load_persona_data(persona_name)
            if not persona_data:
                raise ValueError(f"Persona data not found for {persona_name}")
            
            self.persona_name = persona_name
            self.persona_data = persona_data
            
            transcript = self._prepare_transcript()
            report_text, tokens = await self._generate_full_report(transcript)
            self._total_tokens = tokens
            
            html_report = self._format_html_report(report_text)
            logger.info(f"[SupervisionReport] Generated report for {persona_name}, tokens used: {self._total_tokens}")
            return html_report, self._total_tokens
            
        except Exception as e:
            logger.error(f"[SupervisionReport] Error generating report: {str(e)}", exc_info=True)
            error_html = f"<html><body><p style='color:red'>Error generating report: {str(e)}</p></body></html>"
            return error_html, self._total_tokens

    async def _generate_full_report(self, transcript: str) -> Tuple[Dict, int]:
        """Generate complete report structure with single LLM call"""
        system_prompt = f"""
        Ты опытный супервизор в психотерапии. Проанализируй сессию и составь полный отчет в строго заданном формате.
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.

        Требуемая структура отчета:
        1. Общая характеристика сессии: 5-7 предложений о контакте, защитах клиента, темпе работы
        2. Сильные стороны работы: 4-6 пунктов с объяснениями
        3. Ключевые наблюдения: 3-5 пунктов о клиенте
        4. Зоны для проработки: 3-5 пунктов
        5. Риски: 2-4 пункта
        6. Рекомендации: 5-7 предложений

        Формат ответа в JSON:
        {{
            "general_characteristics": "текст",
            "strengths": ["пункт 1", "пункт 2", ...],
            "observations": ["пункт 1", "пункт 2", ...],
            "areas_for_work": ["пункт 1", "пункт 2", ...],
            "risks": ["пункт 1", "пункт 2", ...],
            "recommendations": "текст"
        }}
        """

        user_prompt = f"""
        Информация о персонаже:
        Имя: {self.persona_data['persona']['name']}
        Возраст: {self.persona_data['persona']['age']}
        Основные проблемы: {', '.join(self.persona_data.get('current_symptoms', {}).keys()) if self.persona_data.get('current_symptoms') else '—'}
        Защитные механизмы: {', '.join(self.persona_data.get('interaction_guide', {}).get('defenses', [])) if self.persona_data.get('interaction_guide', {}).get('defenses') else '—'}

        Транскрипт сессии:
        {transcript}

        Сгенерируй полный отчет в строго указанном JSON-формате.
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=SUPERVISION_REPORT_TEMP,
            response_format="json_object"
        )
        
        try:
            report_data = json.loads(response)
            return report_data, tokens
        except json.JSONDecodeError:
            logger.error(f"[SupervisionReport] Failed to parse LLM response: {response}")
            raise ValueError("Invalid JSON response from LLM")

    def _format_html_report(self, report_data: Dict) -> str:
        """Convert report data to HTML format"""
        # html = f"""
        # <!DOCTYPE html>
        # <html>
        # <head>
        #     <meta charset="UTF-8">
        #     <title>Супервизорский отчёт по клиенту {self.persona_name}</title>
        #     <style>
        #         body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
        #         h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
        #         h2 {{ color: #2980b9; margin-top: 20px; }}
        #         ul {{ padding-left: 20px; }}
        #         li {{ margin-bottom: 5px; }}
        #         .section {{ margin-bottom: 15px; }}
        #     </style>
        # </head>
        # <body>
        #     <h1>Супервизорский отчёт по клиенту {self.persona_name}</h1>
            
        #     <div class="section">
        #         <h2>Общая характеристика сессии</h2>
        #         <p>{report_data['general_characteristics']}</p>
        #     </div>
            
        #     <div class="section">
        #         <h2>Сильные стороны работы</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in report_data['strengths'])}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Ключевые наблюдения</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in report_data['observations'])}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Зоны для дальнейшей проработки</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in report_data['areas_for_work'])}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Риски</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in report_data['risks'])}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Вывод и рекомендации</h2>
        #         <p>{report_data['recommendations']}</p>
        #     </div>
        # </body>
        # </html>
        # """
        telegram_html = f"""
        <b>Супервизорский отчёт по клиенту {self.persona_name}</b>\n\n
        <b>Общая характеристика сессии:</b>\n{report_data['general_characteristics']}\n\n
        <b>Сильные стороны работы:</b>\n{''.join(f'• {item}\n' for item in report_data['strengths'])}\n
        <b>Ключевые наблюдения:</b>\n{''.join(f'• {item}\n' for item in report_data['observations'])}\n
        <b>Зоны для дальнейшей проработки:</b>\n{''.join(f'• {item}\n' for item in report_data['areas_for_work'])}\n
        <b>Риски:</b>\n{''.join(f'• {item}\n' for item in report_data['risks'])}\n\n
        <b>Вывод и рекомендации:</b>\n{report_data['recommendations']}
        """
        return telegram_html

    async def _load_persona_data(self, persona_name: str) -> Optional[Dict]:
        """Load persona data from database"""
        return await self.persona_loader.get_persona(persona_name)

    def _prepare_transcript(self) -> str:
        """Format session history into transcript"""
        return "\n".join(
            f"{msg['role'].capitalize()}: {msg['content']}" 
            for msg in self.session_history
        )