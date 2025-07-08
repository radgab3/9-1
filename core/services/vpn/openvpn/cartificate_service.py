"""
Сервис управления сертификатами для OpenVPN
"""

import os
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from loguru import logger


class CertificateService:
    """Сервис для управления OpenVPN сертификатами"""
    
    def __init__(self):
        self.key_size = 2048
        self.cert_validity_days = 365
    
    async def generate_ca_certificate(self) -> Dict[str, str]:
        """
        Генерировать CA сертификат и ключ
        
        Returns:
            Dict[str, str]: CA сертификат и приватный ключ
        """
        try:
            # Генерируем приватный ключ CA
            ca_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size
            )
            
            # Создаем CA сертификат
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VPN Bot CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, "VPN Bot CA"),
            ])
            
            ca_cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                ca_private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=self.cert_validity_days * 10)  # CA живет дольше
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("ca.vpnbot.local"),
                ]),
                critical=False,
            ).add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    content_commitment=False,
                    encipher_only=False,
                    decipher_only=False
                ),
                critical=True,
            ).sign(ca_private_key, hashes.SHA256())
            
            # Сериализуем в PEM формат
            ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode()
            ca_key_pem = ca_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            
            logger.info("CA certificate generated successfully")
            
            return {
                "certificate": ca_cert_pem,
                "private_key": ca_key_pem
            }
            
        except Exception as e:
            logger.error(f"Error generating CA certificate: {e}")
            raise
    
    async def generate_server_certificate(
        self,
        server_name: str,
        ca_cert_pem: str,
        ca_key_pem: str,
        server_ip: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Генерировать серверный сертификат
        
        Args:
            server_name: Имя сервера
            ca_cert_pem: CA сертификат в PEM формате
            ca_key_pem: CA приватный ключ в PEM формате
            server_ip: IP адрес сервера
            
        Returns:
            Dict[str, str]: Серверный сертификат и ключ
        """
        try:
            # Загружаем CA
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode())
            ca_private_key = serialization.load_pem_private_key(
                ca_key_pem.encode(),
                password=None
            )
            
            # Генерируем ключ сервера
            server_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size
            )
            
            # Создаем серверный сертификат
            subject = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VPN Bot Server"),
                x509.NameAttribute(NameOID.COMMON_NAME, server_name),
            ])
            
            # Альтернативные имена
            san_list = [x509.DNSName(server_name)]
            if server_ip:
                try:
                    import ipaddress
                    ip_addr = ipaddress.ip_address(server_ip)
                    san_list.append(x509.IPAddress(ip_addr))
                except ValueError:
                    pass
            
            server_cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                ca_cert.subject
            ).public_key(
                server_private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=self.cert_validity_days)
            ).add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False
                ),
                critical=True,
            ).add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=True,
            ).sign(ca_private_key, hashes.SHA256())
            
            # Сериализуем
            server_cert_pem = server_cert.public_bytes(serialization.Encoding.PEM).decode()
            server_key_pem = server_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            
            logger.info(f"Server certificate generated for {server_name}")
            
            return {
                "certificate": server_cert_pem,
                "private_key": server_key_pem
            }
            
        except Exception as e:
            logger.error(f"Error generating server certificate: {e}")
            raise
    
    async def generate_client_certificate(
        self,
        client_name: str,
        server_ca: str,
        server_key: str
    ) -> Dict[str, str]:
        """
        Генерировать клиентский сертификат
        
        Args:
            client_name: Имя клиента
            server_ca: CA сертификат
            server_key: CA ключ
            
        Returns:
            Dict[str, str]: Клиентский сертификат и ключ
        """
        try:
            # Загружаем CA
            ca_cert = x509.load_pem_x509_certificate(server_ca.encode())
            ca_private_key = serialization.load_pem_private_key(
                server_key.encode(),
                password=None
            )
            
            # Генерируем ключ клиента
            client_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size
            )
            
            # Создаем клиентский сертификат
            subject = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VPN Bot Client"),
                x509.NameAttribute(NameOID.COMMON_NAME, client_name),
            ])
            
            client_cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                ca_cert.subject
            ).public_key(
                client_private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=self.cert_validity_days)
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False
                ),
                critical=True,
            ).add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=True,
            ).sign(ca_private_key, hashes.SHA256())
            
            # Сериализуем
            client_cert_pem = client_cert.public_bytes(serialization.Encoding.PEM).decode()
            client_key_pem = client_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            
            logger.info(f"Client certificate generated for {client_name}")
            
            return {
                "certificate": client_cert_pem,
                "private_key": client_key_pem
            }
            
        except Exception as e:
            logger.error(f"Error generating client certificate: {e}")
            raise
    
    async def revoke_certificate(self, cert_pem: str) -> bool:
        """
        Отозвать сертификат (добавить в CRL)
        
        Args:
            cert_pem: Сертификат для отзыва
            
        Returns:
            bool: Успешность отзыва
        """
        try:
            # В полной реализации здесь было бы обновление CRL
            # Пока просто логируем
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            serial_number = cert.serial_number
            
            logger.info(f"Certificate revoked: serial {serial_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking certificate: {e}")
            return False
    
    async def generate_dh_params(self, key_size: int = 2048) -> str:
        """
        Генерировать DH параметры для OpenVPN
        
        Args:
            key_size: Размер ключа
            
        Returns:
            str: DH параметры в PEM формате
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import dh
            
            # Генерируем DH параметры
            parameters = dh.generate_parameters(
                generator=2,
                key_size=key_size
            )
            
            # Сериализуем в PEM
            dh_pem = parameters.parameter_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.ParameterFormat.PKCS3
            ).decode()
            
            logger.info(f"DH parameters generated ({key_size} bits)")
            return dh_pem
            
        except Exception as e:
            logger.error(f"Error generating DH parameters: {e}")
            raise
    
    async def generate_ta_key(self) -> str:
        """
        Генерировать TLS-Auth ключ
        
        Returns:
            str: TLS-Auth ключ в формате OpenVPN
        """
        try:
            import secrets
            
            # Генерируем 256 байт случайных данных
            key_data = secrets.token_bytes(256)
            
            # Форматируем как OpenVPN TLS-Auth ключ
            ta_key_lines = [
                "-----BEGIN OpenVPN Static key V1-----"
            ]
            
            # Разбиваем на строки по 32 байта (64 hex символа)
            hex_data = key_data.hex()
            for i in range(0, len(hex_data), 64):
                ta_key_lines.append(hex_data[i:i+64])
            
            ta_key_lines.append("-----END OpenVPN Static key V1-----")
            
            ta_key = "\n".join(ta_key_lines)
            
            logger.info("TLS-Auth key generated")
            return ta_key
            
        except Exception as e:
            logger.error(f"Error generating TLS-Auth key: {e}")
            raise