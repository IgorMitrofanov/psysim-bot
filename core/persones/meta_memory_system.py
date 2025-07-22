import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from core.persones.llm_engine import get_response
from config import logger

class MetaMemorySystem:
    def __init__(self, persona_data: Dict):
        try:
            self.persona_data = persona_data
            self.name = persona_data['persona']['name']
            self.age = persona_data['persona']['age']
            
            # Инициализация памяти пациента
            self.session_summary = ""
            self.key_moments = []
            self.emotional_trajectory = []
            self.disclosures = []  # Важные откровения пациента
            self.resistance_level = persona_data.get("resistance_level", "средний")
            self.last_updated = datetime.now()
            
            logger.info(f"Initialized PatientMemorySystem for {self.name}, age {self.age}")
            logger.debug(f"Initial resistance: {self.resistance_level}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PatientMemorySystem: {str(e)}", exc_info=True)
            raise

    async def update_memory(self, messages: List[Dict]) -> Tuple[str, int]:
        """Обновляет память пациента на основе истории диалога"""
        logger.info(f"{self.name}: Starting memory update")
        try:
            compact_history = self._prepare_history(messages)
            logger.debug(f"{self.name}: Compact history prepared (last {min(8, len(messages))} messages)")
            
            prompt = self._build_patient_memory_prompt(compact_history)
            logger.debug(f"{self.name}: Memory update prompt constructed")
            
            logger.info(f"{self.name}: Requesting memory update from LLM")
            response, tokens = await get_response(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600
            )
            
            memory_update = self._parse_patient_response(response)
            self._apply_memory_update(memory_update)
            self.last_updated = datetime.now()
            
            memory = self.get_compressed_memory()
            logger.info(f"{self.name}: Memory updated successfully")
            logger.debug(f"{self.name}: Current memory state: {memory}")
            
            return memory, tokens
            
        except Exception as e:
            logger.error(f"{self.name}: Memory update failed: {str(e)}", exc_info=True)
            return self.get_compressed_memory(), 0

    def _prepare_history(self, messages: List[Dict]) -> str:
        """Подготавливает историю диалога для анализа"""
        try:
            history = "\n".join(
                f"{msg['role'].upper()}: {msg['content']}" 
                for msg in messages[-10:]  # Берем больше контекста для пациента
            )
            return history
        except Exception as e:
            logger.error(f"{self.name}: History preparation error: {str(e)}")
            raise

    def _build_patient_memory_prompt(self, history: str) -> str:
        """Строит промпт для обновления памяти пациента"""
        background = self.persona_data.get("background", "—")
        trauma_text = "\n".join(f"- {item}" for item in self.persona_data.get("trauma_history", [])) or "—"
        logger.info(f"memory prompt history {history}")
        prompt = f"""
        [РОЛЬ]
        Ты {self.name}, {self.age} лет, пациент на психотерапии. Проанализируй текущую сессию со своей субъективной точки зрения.

        [БИОГРАФИЧЕСКИЙ КОНТЕКСТ]
        {background}
        
        [ТРАВМАТИЧЕСКИЙ ОПЫТ]
        {trauma_text}

        [ИСТОРИЯ СЕССИИ]
        {history}

        [ИНСТРУКЦИИ]
        Ответь строго в формате:

        ### SUMMARY
        Как ты сам(а) оцениваешь прогресс сессии? (3-5 предложений)

        ### KEY MOMENTS
        - Самые значимые для тебя моменты
        - Что вызвало сильные эмоции?
        - Что было трудно обсуждать?

        ### EMOTIONAL STATE
        Твое текущее эмоциональное состояние (детально)

        ### RESISTANCE
        Уровень сопротивления: низкий/средний/высокий

        ### DISCLOSURES
        - Что ты раскрыл(а) терапевту
        - О чем пожалел(а), что сказал(а)
        - О чем хотел(а) бы сказать, но не решился(ась)

        ### NEXT SESSION
        - Что хочешь обсудить в следующий раз
        - Какие вопросы остались
        """
        return prompt

    def _parse_patient_response(self, response: str) -> Dict:
        """Парсит ответ пациента в структурированный формат"""
        try:
            def extract_section(title: str) -> str:
                match = re.search(fr"### {title}\n(.*?)(?=### |$)", response, re.DOTALL)
                return match.group(1).strip() if match else ""

            def parse_list(text: str) -> List[str]:
                return [item.strip() for item in text.split("-") if item.strip()]

            parsed = {
                "summary": extract_section("SUMMARY"),
                "key_moments": parse_list(extract_section("KEY MOMENTS")),
                "emotional_state": extract_section("EMOTIONAL STATE"),
                "resistance": extract_section("RESISTANCE"),
                "disclosures": parse_list(extract_section("DISCLOSURES")),
                "next_session": parse_list(extract_section("NEXT SESSION"))
            }
            
            logger.debug(f"{self.name}: Parsed memory update: {parsed}")
            return parsed
            
        except Exception as e:
            logger.error(f"{self.name}: Failed to parse response: {str(e)}")
            return {}

    def _apply_memory_update(self, update: Dict):
        """Применяет обновления к памяти пациента"""
        try:
            if update.get("summary"):
                self.session_summary = update["summary"]
                
            if update.get("key_moments"):
                self.key_moments = update["key_moments"][:5]
                
            if update.get("emotional_state"):
                self.emotional_trajectory.append(update["emotional_state"])
                
            if update.get("resistance"):
                self.resistance_level = update["resistance"]
                logger.info(f"{self.name}: Resistance level changed to {self.resistance_level}")
                
            if update.get("disclosures"):
                self.disclosures.extend(update["disclosures"])
                
            logger.debug(f"{self.name}: Memory update applied successfully")
            
        except Exception as e:
            logger.error(f"{self.name}: Failed to apply memory update: {str(e)}")

    def get_compressed_memory(self) -> str:
        """Возвращает сжатую версию памяти пациента"""
        try:
            current_emotion = self.emotional_trajectory[-1] if self.emotional_trajectory else "не определено"
            
            compressed = (
                f"СЕССИЯ: {self.session_summary}\n"
                f"ЭМОЦИИ: {current_emotion}\n"
                f"СОПРОТИВЛЕНИЕ: {self.resistance_level}\n"
                f"КЛЮЧЕВЫЕ МОМЕНТЫ: {', '.join(self.key_moments[:3])}\n"
                f"РАСКРЫТИЯ: {len(self.disclosures)} важных откровений"
            )
            return compressed
            
        except Exception as e:
            logger.error(f"{self.name}: Failed to compress memory: {str(e)}")
            return "Ошибка формирования памяти"