"""
Генератор QR кодов для VPN конфигураций
"""

import qrcode
import base64
from io import BytesIO
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from loguru import logger

from config.settings import settings


class QRCodeGenerator:
    """Генератор QR кодов для VPN конфигураций"""
    
    def __init__(self):
        self.output_dir = Path(settings.QR_CODES_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Настройки QR кода
        self.qr_settings = {
            "version": 1,
            "error_correction": qrcode.constants.ERROR_CORRECT_L,
            "box_size": 10,
            "border": 4
        }
        
        # Цветовая схема
        self.colors = {
            "vless": {"fill": "#2E7D32", "back": "#E8F5E8"},
            "vmess": {"fill": "#1976D2", "back": "#E3F2FD"},
            "trojan": {"fill": "#7B1FA2", "back": "#F3E5F5"},
            "openvpn": {"fill": "#F57C00", "back": "#FFF3E0"},
            "wireguard": {"fill": "#5D4037", "back": "#EFEBE9"},
            "default": {"fill": "#424242", "back": "#F5F5F5"}
        }
    
    async def generate_qr_code(
        self,
        connection_string: str,
        config_id: int,
        protocol: str = "vless",
        add_logo: bool = True,
        add_labels: bool = True
    ) -> Optional[str]:
        """
        Генерировать QR код для VPN конфигурации
        
        Args:
            connection_string: Строка подключения
            config_id: ID конфигурации
            protocol: Протокол VPN
            add_logo: Добавить логотип
            add_labels: Добавить подписи
            
        Returns:
            Optional[str]: Путь к файлу QR кода
        """
        try:
            # Получаем цветовую схему для протокола
            colors = self.colors.get(protocol.lower(), self.colors["default"])
            
            # Создаем QR код
            qr = qrcode.QRCode(**self.qr_settings)
            qr.add_data(connection_string)
            qr.make(fit=True)
            
            # Создаем изображение QR кода
            qr_image = qr.make_image(
                fill_color=colors["fill"],
                back_color=colors["back"]
            ).convert('RGB')
            
            # Добавляем логотип если требуется
            if add_logo:
                qr_image = await self._add_logo(qr_image, protocol)
            
            # Добавляем подписи если требуется
            if add_labels:
                qr_image = await self._add_labels(qr_image, protocol, config_id)
            
            # Сохраняем файл
            filename = f"qr_config_{config_id}_{protocol}.png"
            filepath = self.output_dir / filename
            
            qr_image.save(filepath, "PNG", quality=95)
            
            logger.info(f"QR code generated: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            return None
    
    async def generate_qr_code_base64(
        self,
        connection_string: str,
        protocol: str = "vless"
    ) -> Optional[str]:
        """
        Генерировать QR код в формате base64
        
        Args:
            connection_string: Строка подключения
            protocol: Протокол VPN
            
        Returns:
            Optional[str]: QR код в base64
        """
        try:
            colors = self.colors.get(protocol.lower(), self.colors["default"])
            
            qr = qrcode.QRCode(**self.qr_settings)
            qr.add_data(connection_string)
            qr.make(fit=True)
            
            qr_image = qr.make_image(
                fill_color=colors["fill"],
                back_color=colors["back"]
            )
            
            # Конвертируем в base64
            buffer = BytesIO()
            qr_image.save(buffer, format='PNG')
            buffer.seek(0)
            
            base64_string = base64.b64encode(buffer.read()).decode()
            return f"data:image/png;base64,{base64_string}"
            
        except Exception as e:
            logger.error(f"Error generating base64 QR code: {e}")
            return None
    
    async def _add_logo(self, qr_image: Image.Image, protocol: str) -> Image.Image:
        """
        Добавить логотип к QR коду
        
        Args:
            qr_image: Изображение QR кода
            protocol: Протокол VPN
            
        Returns:
            Image.Image: QR код с логотипом
        """
        try:
            # Создаем простой логотип из текста протокола
            logo_size = min(qr_image.size) // 6
            logo = Image.new('RGBA', (logo_size, logo_size), (255, 255, 255, 0))
            draw = ImageDraw.Draw(logo)
            
            # Рисуем фон логотипа
            colors = self.colors.get(protocol.lower(), self.colors["default"])
            draw.rectangle([0, 0, logo_size, logo_size], fill=colors["fill"])
            
            # Добавляем текст протокола
            try:
                font_size = logo_size // 4
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                font = ImageFont.load_default()
            
            text = protocol.upper()[:4]  # Максимум 4 символа
            
            # Центрируем текст
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            text_x = (logo_size - text_width) // 2
            text_y = (logo_size - text_height) // 2
            
            draw.text((text_x, text_y), text, fill="white", font=font)
            
            # Накладываем логотип на QR код
            qr_width, qr_height = qr_image.size
            logo_x = (qr_width - logo_size) // 2
            logo_y = (qr_height - logo_size) // 2
            
            qr_image.paste(logo, (logo_x, logo_y), logo)
            
            return qr_image
            
        except Exception as e:
            logger.error(f"Error adding logo: {e}")
            return qr_image
    
    async def _add_labels(
        self, 
        qr_image: Image.Image, 
        protocol: str, 
        config_id: int
    ) -> Image.Image:
        """
        Добавить подписи к QR коду
        
        Args:
            qr_image: Изображение QR кода
            protocol: Протокол VPN
            config_id: ID конфигурации
            
        Returns:
            Image.Image: QR код с подписями
        """
        try:
            # Создаем новое изображение с местом для подписей
            padding = 60
            new_width = qr_image.width
            new_height = qr_image.height + padding * 2
            
            colors = self.colors.get(protocol.lower(), self.colors["default"])
            labeled_image = Image.new('RGB', (new_width, new_height), colors["back"])
            
            # Вставляем QR код
            labeled_image.paste(qr_image, (0, padding))
            
            # Добавляем подписи
            draw = ImageDraw.Draw(labeled_image)
            
            try:
                title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
                subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
            
            # Заголовок
            title = f"{protocol.upper()} VPN Configuration"
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (new_width - title_width) // 2
            
            draw.text((title_x, 10), title, fill=colors["fill"], font=title_font)
            
            # Подзаголовок
            subtitle = f"Config ID: {config_id}"
            subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
            subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
            subtitle_x = (new_width - subtitle_width) // 2
            
            draw.text((subtitle_x, 35), subtitle, fill=colors["fill"], font=subtitle_font)
            
            # Инструкция внизу
            instruction = "Scan with VPN app"
            instruction_bbox = draw.textbbox((0, 0), instruction, font=subtitle_font)
            instruction_width = instruction_bbox[2] - instruction_bbox[0]
            instruction_x = (new_width - instruction_width) // 2
            instruction_y = new_height - 25
            
            draw.text((instruction_x, instruction_y), instruction, fill=colors["fill"], font=subtitle_font)
            
            return labeled_image
            
        except Exception as e:
            logger.error(f"Error adding labels: {e}")
            return qr_image
    
    async def generate_batch_qr_codes(
        self,
        configurations: list[Dict[str, Any]]
    ) -> Dict[int, str]:
        """
        Генерировать QR коды для нескольких конфигураций
        
        Args:
            configurations: Список конфигураций
            
        Returns:
            Dict[int, str]: Словарь config_id -> путь к файлу
        """
        results = {}
        
        for config in configurations:
            config_id = config.get("id")
            connection_string = config.get("connection_string")
            protocol = config.get("protocol", "vless")
            
            if config_id and connection_string:
                qr_path = await self.generate_qr_code(
                    connection_string=connection_string,
                    config_id=config_id,
                    protocol=protocol
                )
                
                if qr_path:
                    results[config_id] = qr_path
        
        logger.info(f"Generated {len(results)} QR codes")
        return results
    
    async def create_instruction_image(
        self,
        protocol: str,
        instructions: list[str]
    ) -> Optional[str]:
        """
        Создать изображение с инструкциями по настройке
        
        Args:
            protocol: Протокол VPN
            instructions: Список инструкций
            
        Returns:
            Optional[str]: Путь к файлу с инструкциями
        """
        try:
            colors = self.colors.get(protocol.lower(), self.colors["default"])
            
            # Размеры изображения
            width = 600
            line_height = 30
            padding = 40
            height = padding * 2 + len(instructions) * line_height + 100
            
            # Создаем изображение
            image = Image.new('RGB', (width, height), colors["back"])
            draw = ImageDraw.Draw(image)
            
            try:
                title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
                text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except:
                title_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
            
            # Заголовок
            title = f"Setup Instructions - {protocol.upper()}"
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (width - title_width) // 2
            
            draw.text((title_x, padding), title, fill=colors["fill"], font=title_font)
            
            # Инструкции
            y_position = padding + 60
            for i, instruction in enumerate(instructions, 1):
                text = f"{i}. {instruction}"
                draw.text((padding, y_position), text, fill="#333333", font=text_font)
                y_position += line_height
            
            # Сохраняем файл
            filename = f"instructions_{protocol}.png"
            filepath = self.output_dir / filename
            
            image.save(filepath, "PNG", quality=95)
            
            logger.info(f"Instruction image created: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error creating instruction image: {e}")
            return None
    
    def cleanup_old_qr_codes(self, days: int = 7):
        """
        Очистить старые QR коды
        
        Args:
            days: Количество дней для хранения
        """
        try:
            import time
            
            cutoff_time = time.time() - (days * 24 * 3600)
            removed_count = 0
            
            for file_path in self.output_dir.glob("*.png"):
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    removed_count += 1
            
            logger.info(f"Cleaned up {removed_count} old QR codes")
            
        except Exception as e:
            logger.error(f"Error cleaning up QR codes: {e}")


# Глобальный экземпляр генератора
qr_generator = QRCodeGenerator()


async def generate_config_qr(
    connection_string: str,
    config_id: int,
    protocol: str = "vless"
) -> Optional[str]:
    """
    Быстрая функция для генерации QR кода конфигурации
    
    Args:
        connection_string: Строка подключения
        config_id: ID конфигурации
        protocol: Протокол
        
    Returns:
        Optional[str]: Путь к QR коду
    """
    return await qr_generator.generate_qr_code(
        connection_string=connection_string,
        config_id=config_id,
        protocol=protocol
    )


async def generate_qr_base64(
    connection_string: str,
    protocol: str = "vless"
) -> Optional[str]:
    """
    Быстрая функция для генерации QR кода в base64
    
    Args:
        connection_string: Строка подключения
        protocol: Протокол
        
    Returns:
        Optional[str]: QR код в base64
    """
    return await qr_generator.generate_qr_code_base64(
        connection_string=connection_string,
        protocol=protocol
    )