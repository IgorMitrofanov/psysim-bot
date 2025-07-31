from typing import Dict, List, Optional, Tuple
from config import logger
from core.persones.llm_engine import call_llm_for_meta_ai

SUPERVISION_REPORT_TEMP = 0.9

class SimpleSupervisionReportBuilder:
    def __init__(self, persona_loader, session_history: List[Dict]):
        self.session_history = session_history
        self.persona_loader = persona_loader
        self._total_tokens = 0

    async def generate_report(self, persona_name: str) -> Tuple[str, int]:
        """
        Generate a comprehensive supervision report in HTML format with single LLM call.
        
        Args:
            persona_name: Name of the persona (bot/patient) to generate report for
            
        Returns:
            Tuple of (HTML_report, total_tokens_used)
        """
        try:
            # Load persona data
            persona_data = await self._load_persona_data(persona_name)
            if not persona_data:
                raise ValueError(f"Persona data not found for {persona_name}")
            
            self.persona_name = persona_name
            self.persona_data = persona_data
            
            # Prepare session transcript
            transcript = self._prepare_transcript()
            
            # Generate all report sections in one LLM call
            report_data, tokens = await self._generate_all_sections(transcript)
            self._total_tokens = tokens
            
            # Format as HTML
            html_report = self._format_html_report(
                report_data['general_char'],
                report_data['strengths'],
                report_data['observations'],
                report_data['areas_for_work'],
                report_data['risks'],
                report_data['recommendations']
            )
            
            logger.info(f"[SupervisionReport] Generated report for {persona_name}, tokens used: {self._total_tokens}")
            return html_report, self._total_tokens
            
        except Exception as e:
            logger.error(f"[SupervisionReport] Error generating report: {str(e)}", exc_info=True)
            error_html = f"<html><body><p style='color:red'>Error generating report: {str(e)}</p></body></html>"
            return error_html, self._total_tokens

    async def _generate_all_sections(self, transcript: str) -> Tuple[Dict, int]:
        """Generate all report sections in a single LLM call."""
        system_prompt = f"""
        Ты опытный супервизор в психотерапии. Проанализируй сессию и подготовь полный отчет в строго заданном формате.
        
        Клиент:
        Имя: {self.persona_data['persona']['name']}
        Возраст: {self.persona_data['persona']['age']}
        Основные проблемы: {', '.join(self.persona_data.get('current_symptoms', {}).keys()) if self.persona_data.get('current_symptoms') else '—'}
        
        Требуется подготовить отчет со следующими разделами:
        
        1. Общая характеристика сессии (5-7 предложений)
        - Опиши как устанавливался контакт
        - Какие защиты проявлял клиент
        - Как терапевт работал с сопротивлением
        - Темп и глубину раскрытия клиента
        - Уровень безопасности в сессии
        
        2. Сильные стороны работы терапевта (3-5 пунктов)
        - Контейнирование эмоций
        - Удержание границ
        - Подход к раннему опыту
        - Эмпатическое отражение
        - Работа с сопротивлением
        
        3. Ключевые наблюдения о клиенте (3-5 пунктов)
        - Внутренние конфликты
        - Паттерны отношений
        - Проявляющиеся защиты
        - Основные эмоциональные темы
        
        4. Зоны для дальнейшей проработки (3-5 пунктов)
        - Неразрешенные конфликты
        - Темы, которых избегал клиент
        - Повторяющиеся проблемные паттерны
        
        5. Потенциальные риски (2-3 пункта)
        - Формы сопротивления
        - Риск прекращения терапии
        - Сложные для клиента темы
        
        6. Рекомендации (5-7 предложений)
        - Темп терапии
        - Подходящие подходы
        - Работа с сопротивлением
        - Поддержание альянса
        
        Формат ответа (ВСЕГДА ПРИДЕРЖИВАЙСЯ ЭТОГО ФОРМАТА):
        
        [ОБЩАЯ ХАРАКТЕРИСТИКА]
        <текст характеристики>
        
        [СИЛЬНЫЕ СТОРОНЫ]
        - Пункт 1
        - Пункт 2
        - ...
        
        [НАБЛЮДЕНИЯ]
        - Пункт 1
        - Пункт 2
        - ...
        
        [ЗОНЫ ДЛЯ ПРОРАБОТКИ]
        - Пункт 1
        - Пункт 2
        - ...
        
        [РИСКИ]
        - Пункт 1
        - Пункт 2
        - ...
        
        [РЕКОМЕНДАЦИИ]
        <текст рекомендаций>
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=f"Транскрипт сессии:\n{transcript}",
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        # Parse the response into sections
        report_data = self._parse_llm_response(response)
        return report_data, tokens

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse the LLM response into structured data."""
        sections = {
            'general_char': '',
            'strengths': [],
            'observations': [],
            'areas_for_work': [],
            'risks': [],
            'recommendations': ''
        }
        
        current_section = None
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].lower()
                if current_section == 'сильные стороны':
                    current_section = 'strengths'
                elif current_section == 'наблюдения':
                    current_section = 'observations'
                elif current_section == 'зоны для проработки':
                    current_section = 'areas_for_work'
                elif current_section == 'риски':
                    current_section = 'risks'
                elif current_section == 'общая характеристика':
                    current_section = 'general_char'
                elif current_section == 'рекомендации':
                    current_section = 'recommendations'
            else:
                if current_section in ['strengths', 'observations', 'areas_for_work', 'risks']:
                    if line.startswith('-'):
                        sections[current_section].append(line[1:].strip())
                elif current_section in ['general_char', 'recommendations']:
                    sections[current_section] += line + '\n'
        
        # Clean up the text sections
        sections['general_char'] = sections['general_char'].strip()
        sections['recommendations'] = sections['recommendations'].strip()
        
        return sections

    def _format_html_report(self, general_char: str, strengths: List[str], 
                          observations: List[str], areas_for_work: List[str],
                          risks: List[str], recommendations: str) -> str:
        """Format all sections into a professional HTML report."""
        telegram_html = f"""
        <b>Супервизорский отчёт по клиенту {self.persona_name}</b>\n\n
        <b>Общая характеристика сессии:</b>\n{general_char}\n\n
        <b>Сильные стороны работы:</b>\n{''.join(f'• {item}\n' for item in strengths)}\n
        <b>Ключевые наблюдения:</b>\n{''.join(f'• {item}\n' for item in observations)}\n
        <b>Зоны для дальнейшей проработки:</b>\n{''.join(f'• {item}\n' for item in areas_for_work)}\n
        <b>Риски:</b>\n{''.join(f'• {item}\n' for item in risks)}\n\n
        <b>Вывод и рекомендации:</b>\n{recommendations}
        """
        return telegram_html

    async def _load_persona_data(self, persona_name: str) -> Optional[Dict]:
        """Load persona data from database using PersonaLoader."""
        return await self.persona_loader.get_persona(persona_name)

    def _prepare_transcript(self) -> str:
        """Format the session history into a readable transcript."""
        return "\n".join(
            f"{msg['role'].capitalize()}: {msg['content']}" 
            for msg in self.session_history
        )