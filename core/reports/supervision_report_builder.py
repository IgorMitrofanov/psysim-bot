from typing import Dict, List, Optional, Tuple
from config import logger
from core.persones.llm_engine import call_llm_for_meta_ai

SUPERVISION_REPORT_TEMP = 0.9

class SupervisionReportBuilder:
    def __init__(self, persona_loader, session_history: List[Dict]):
        """
        Initialize the supervision report builder with database engine and session history.
        
        Args:
            persona_loader: 
            session_history: List of message dicts from the therapy session
        """
        self.session_history = session_history
        self.persona_loader = persona_loader
        self._total_tokens = 0

    async def generate_report(self, persona_name: str) -> Tuple[str, int]:
        """
        Generate a comprehensive supervision report in HTML format based on the session.
        
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
            
            # Generate report sections
            general_char, tokens1 = await self._generate_general_characteristics(transcript)
            strengths, tokens2 = await self._generate_strengths(transcript)
            observations, tokens3 = await self._generate_observations(transcript)
            areas_for_work, tokens4 = await self._generate_areas_for_work(transcript)
            risks, tokens5 = await self._generate_risks(transcript)
            recommendations, tokens6 = await self._generate_recommendations(transcript)
            
            self._total_tokens = tokens1 + tokens2 + tokens3 + tokens4 + tokens5 + tokens6
            
            # Format as HTML
            html_report = self._format_html_report(
                general_char,
                strengths,
                observations,
                areas_for_work,
                risks,
                recommendations
            )
            
            logger.info(f"[SupervisionReport] Generated report for {persona_name}, tokens used: {self._total_tokens}")
            return html_report, self._total_tokens
            
        except Exception as e:
            logger.error(f"[SupervisionReport] Error generating report: {str(e)}", exc_info=True)
            error_html = f"<html><body><p style='color:red'>Error generating report: {str(e)}</p></body></html>"
            return error_html, self._total_tokens

    def _format_html_report(self, general_char: str, strengths: List[str], 
                          observations: List[str], areas_for_work: List[str],
                          risks: List[str], recommendations: str) -> str:
        """Format all sections into a professional HTML report."""
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
        #         <p>{general_char}</p>
        #     </div>
            
        #     <div class="section">
        #         <h2>Сильные стороны работы</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in strengths)}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Ключевые наблюдения</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in observations)}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Зоны для дальнейшей проработки</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in areas_for_work)}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Риски</h2>
        #         <ul>
        #             {''.join(f'<li>{item}</li>' for item in risks)}
        #         </ul>
        #     </div>
            
        #     <div class="section">
        #         <h2>Вывод и рекомендации</h2>
        #         <p>{recommendations}</p>
        #     </div>
        # </body>
        # </html>
        # """
        
        telegram_html = f"""
        <b>Супервизорский отчёт по клиенту {self.persona_name}</b>\n\n
        <b>Общая характеристика сессии:</b>\n{general_char}\n\n
        <b>Сильные и слабые стороны работы:</b>\n{''.join(f'• {item}\n' for item in strengths)}\n
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

    async def _generate_general_characteristics(self, transcript: str) -> Tuple[str, int]:
        """Generate general session characteristics."""
        system_prompt = f"""
        Ты опытный супервизор в психотерапии. Проанализируй сессию и дай общую характеристику.
        Опиши, как устанавливался контакт, какие защиты проявлял клиент, как терапевт работал с сопротивлением.
        Укажи темп и глубину раскрытия клиента, уровень безопасности в сессии.
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.
        """
        
        user_prompt = f"""
        Информация о персонаже (клиенте):
        Имя: {self.persona_data['persona']['name']}
        Возраст: {self.persona_data['persona']['age']}
        Основные проблемы: {', '.join(self.persona_data.get('current_symptoms', {}).keys()) if self.persona_data.get('current_symptoms') else '—'}
        Механизмы защиты: {', '.join(self.persona_data.get('interaction_guide', {}).get('defenses', [])) if self.persona_data.get('interaction_guide', {}).get('defenses') else '—'}
        
        Транскрипт сессии:
        {transcript}
        
        Дай развернутую характеристику сессии (5-7 предложений), отмечая ключевые моменты.
        Формат: обычный текст, без заголовков.
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        return response.strip(), tokens

    async def _generate_strengths(self, transcript: str) -> Tuple[List[str], int]:
        """Identify therapeutic strengths in the session."""
        system_prompt = """
        Ты супервизор, анализирующий работу терапевта. Выдели сильные и слабые стороны работы терапевта в этой сессии.
        Обрати внимание на:
        - Контейнирование эмоций
        - Удержание границ
        - Подход к раннему опыту
        - Эмпатическое отражение
        - Работу с сопротивлением
        - Поддержание терапевтического альянса
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.
        
        Формат: каждый пункт должен быть полным предложением с объяснением (например: "Контейнирование уязвимости: терапевт не спешит с интерпретациями...").
        Верни только список пунктов, каждый с новой строки, начинающийся с "-".
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=f"Транскрипт сессии:\n{transcript}",
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        return self._format_list_response(response), tokens

    async def _generate_observations(self, transcript: str) -> Tuple[List[str], int]:
        """Generate key clinical observations about the client."""
        system_prompt = f"""
        На основе сессии выдели ключевые наблюдения о персонаже ({self.persona_name}).
        Обрати внимание на:
        - Внутренние конфликты
        - Паттерны отношений
        - Проявляющиеся защиты
        - Основные эмоциональные темы
        - Актуальные запросы
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.
        
        Формат: каждый пункт должен быть полным предложением. Верни только список пунктов, каждый с новой строки, начинающийся с "-".
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=f"Транскрипт сессии:\n{transcript}",
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        return self._format_list_response(response), tokens

    async def _generate_areas_for_work(self, transcript: str) -> Tuple[List[str], int]:
        """Identify areas for further therapeutic work."""
        system_prompt = f"""
        Определи зоны для дальнейшей проработки с персонажем ({self.persona_name}).
        Учитывай:
        - Неразрешенные конфликты
        - Темы, которых избегал клиент
        - Повторяющиеся проблемные паттерны
        - Области для развития
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.
        
        Формат: каждый пункт должен быть полным предложением. Верни только список пунктов, каждый с новой строки, начинающийся с "-".
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=f"Транскрипт сессии:\n{transcript}",
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        return self._format_list_response(response), tokens

    async def _generate_risks(self, transcript: str) -> Tuple[List[str], int]:
        """Identify potential risks in the therapeutic process."""
        system_prompt = f"""
        Определи потенциальные риски в терапии с персонажем ({self.persona_name}).
        Учитывай:
        - Возможные формы сопротивления
        - Риск преждевременного прекращения терапии
        - Сложные для клиента темы
        - Возможные контрпереносы терапевта
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.
        
        Формат: каждый пункт должен быть полным предложением. Верни только список пунктов, каждый с новой строки, начинающийся с "-".
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=f"Транскрипт сессии:\n{transcript}",
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        return self._format_list_response(response), tokens

    async def _generate_recommendations(self, transcript: str) -> Tuple[str, int]:
        """Generate therapeutic recommendations."""
        system_prompt = f"""
        Сформулируй рекомендации для дальнейшей работы с персонажем ({self.persona_name}).
        Учитывай:
        - Темп терапии
        - Подходящие терапевтические подходы
        - Особенности работы с сопротивлением
        - Поддержание терапевтического альянса
        
        Если терапевт ведет себя неподобающе, обязательно обозначь это в отчете.
        
        Дай развернутые рекомендации (5-7 предложений) в формате обычного текста без заголовков.
        """
        
        response, tokens = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=f"Транскрипт сессии:\n{transcript}",
            temperature=SUPERVISION_REPORT_TEMP,
            max_tokens=None
        )
        
        return response.strip(), tokens

    def _format_list_response(self, text: str) -> List[str]:
        """Format LLM list response into clean list items."""
        return [line.strip()[2:] for line in text.split("\n") if line.strip().startswith("-")]