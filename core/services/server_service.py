"""
Сервис для управления VPN серверами
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.database.models import Server, VpnProtocol, User
from core.database.repositories import RepositoryManager
from core.services.vpn.vpn_factory import VpnServiceManager, VpnServiceFactory
from core.exceptions.vpn_exceptions import VpnServerNotAvailableError
from config.settings import settings


class ServerService:
    """Сервис для управления VPN серверами"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.vpn_manager = VpnServiceManager(session)
    
    async def get_all_servers(self, include_inactive: bool = False) -> List[Server]:
        """
        Получить все серверы
        
        Args:
            include_inactive: Включить неактивные серверы
            
        Returns:
            List[Server]: Список серверов
        """
        if include_inactive:
            # Здесь нужен метод для получения всех серверов
            return await self.repos.servers.get_all_active()  # Пока используем активные
        else:
            return await self.repos.servers.get_all_active()
    
    async def get_server_by_id(self, server_id: int) -> Optional[Server]:
        """
        Получить сервер по ID
        
        Args:
            server_id: ID сервера
            
        Returns:
            Optional[Server]: Сервер
        """
        return await self.repos.servers.get_by_id(server_id)
    
    async def get_best_server_for_user(
        self,
        user: User,
        protocol: Optional[VpnProtocol] = None
    ) -> Optional[Server]:
        """
        Получить лучший сервер для пользователя
        
        Args:
            user: Пользователь
            protocol: Предпочитаемый протокол
            
        Returns:
            Optional[Server]: Лучший сервер
        """
        try:
            # Получаем серверы по протоколу
            if protocol:
                servers = await self.repos.servers.get_by_protocol(protocol)
            else:
                servers = await self.repos.servers.get_all_active()
            
            if not servers:
                return None
            
            # Фильтруем серверы по географии для российских пользователей
            if user.country_code in settings.RUSSIA_COUNTRY_CODES:
                preferred_countries = ["NL", "DE", "FI", "LV", "EE", "SE"]
                preferred_servers = [s for s in servers if s.country_code in preferred_countries]
                if preferred_servers:
                    servers = preferred_servers
            
            # Выбираем сервер с наименьшей нагрузкой
            best_server = None
            best_load = float('inf')
            
            for server in servers:
                load = await self._calculate_server_load(server)
                if load < best_load and load < 0.9:  # Не перегруженный сервер
                    best_load = load
                    best_server = server
            
            return best_server
            
        except Exception as e:
            logger.error(f"Error selecting best server for user {user.id}: {e}")
            return None
    
    async def _calculate_server_load(self, server: Server) -> float:
        """
        Рассчитать нагрузку сервера
        
        Args:
            server: Сервер
            
        Returns:
            float: Нагрузка (0.0 - 1.0)
        """
        try:
            # Нагрузка по пользователям
            user_load = server.current_users / server.max_users if server.max_users > 0 else 0
            
            # Нагрузка по CPU
            cpu_load = float(server.cpu_usage) / 100.0
            
            # Нагрузка по памяти
            memory_load = float(server.memory_usage) / 100.0
            
            # Общая нагрузка (взвешенная)
            total_load = (user_load * 0.5) + (cpu_load * 0.3) + (memory_load * 0.2)
            
            return min(total_load, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating server load: {e}")
            return 1.0  # Максимальная нагрузка в случае ошибки
    
    async def update_server_stats(self, server_id: int) -> bool:
        """
        Обновить статистику сервера
        
        Args:
            server_id: ID сервера
            
        Returns:
            bool: Успешность обновления
        """
        try:
            server = await self.repos.servers.get_by_id(server_id)
            if not server:
                return False
            
            # Получаем статистику через VPN сервисы
            stats = {}
            
            # Пробуем получить статистику через каждый поддерживаемый протокол
            for protocol_str in server.supported_protocols:
                try:
                    protocol = VpnProtocol(protocol_str)
                    if VpnServiceFactory.is_protocol_supported(protocol):
                        service = self.vpn_manager.get_service(protocol, server)
                        
                        # Получаем информацию о сервере
                        if hasattr(service, 'get_server_info'):
                            server_info = await service.get_server_info()
                            if server_info:
                                stats.update(server_info)
                                break
                        
                except Exception as e:
                    logger.warning(f"Failed to get stats via {protocol_str}: {e}")
                    continue
            
            # Обновляем статистику в базе данных
            update_data = {
                "last_check": datetime.utcnow()
            }
            
            if stats:
                if "cpu" in stats:
                    update_data["cpu_usage"] = stats["cpu"]
                if "memory" in stats:
                    update_data["memory_usage"] = stats["memory"]
                if "disk" in stats:
                    update_data["disk_usage"] = stats["disk"]
                if "total_clients" in stats:
                    update_data["current_users"] = stats["total_clients"]
            
            success = await self.repos.servers.update_stats(server_id, **update_data)
            
            # Записываем статистику в историю
            if stats:
                await self.repos.server_stats.record_stats(
                    server_id=server_id,
                    active_connections=update_data.get("current_users", 0),
                    cpu_usage=update_data.get("cpu_usage", 0),
                    memory_usage=update_data.get("memory_usage", 0),
                    disk_usage=update_data.get("disk_usage", 0)
                )
            
            await self.repos.commit()
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error updating server stats {server_id}: {e}")
            return False
    
    async def update_all_server_stats(self) -> int:
        """
        Обновить статистику всех активных серверов
        
        Returns:
            int: Количество обновленных серверов
        """
        try:
            servers = await self.repos.servers.get_all_active()
            updated_count = 0
            
            # Создаем задачи для параллельного обновления
            tasks = []
            for server in servers:
                task = asyncio.create_task(self.update_server_stats(server.id))
                tasks.append(task)
            
            # Выполняем задачи с ограничением времени
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Подсчитываем успешные обновления
            for result in results:
                if isinstance(result, bool) and result:
                    updated_count += 1
                elif isinstance(result, Exception):
                    logger.error(f"Server stats update failed: {result}")
            
            logger.info(f"Updated stats for {updated_count}/{len(servers)} servers")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating all server stats: {e}")
            return 0
    
    async def check_server_health(self, server_id: int) -> Dict[str, Any]:
        """
        Проверить здоровье сервера
        
        Args:
            server_id: ID сервера
            
        Returns:
            Dict[str, Any]: Результаты проверки здоровья
        """
        try:
            server = await self.repos.servers.get_by_id(server_id)
            if not server:
                return {"healthy": False, "error": "Server not found"}
            
            health_status = {
                "server_id": server_id,
                "healthy": True,
                "checks": {},
                "overall_status": "healthy",
                "last_check": datetime.utcnow().isoformat()
            }
            
            # Проверка активности сервера
            health_status["checks"]["server_active"] = {
                "status": "pass" if server.is_active else "fail",
                "message": "Server is active" if server.is_active else "Server is inactive"
            }
            
            # Проверка технического обслуживания
            health_status["checks"]["maintenance_mode"] = {
                "status": "pass" if not server.is_maintenance else "warn",
                "message": "Not in maintenance" if not server.is_maintenance else "In maintenance mode"
            }
            
            # Проверка нагрузки
            load = await self._calculate_server_load(server)
            load_status = "pass" if load < 0.8 else "warn" if load < 0.95 else "fail"
            health_status["checks"]["server_load"] = {
                "status": load_status,
                "message": f"Server load: {load:.2%}",
                "value": load
            }
            
            # Проверка доступности через VPN сервисы
            vpn_checks = {}
            for protocol_str in server.supported_protocols:
                try:
                    protocol = VpnProtocol(protocol_str)
                    if VpnServiceFactory.is_protocol_supported(protocol):
                        service = self.vpn_manager.get_service(protocol, server)
                        
                        # Тестируем соединение
                        if hasattr(service, 'test_connection'):
                            connection_ok = await service.test_connection(0)  # Dummy config ID
                            vpn_checks[protocol_str] = {
                                "status": "pass" if connection_ok else "fail",
                                "message": f"{protocol_str.upper()} connection test"
                            }
                        else:
                            # Проверяем валидность конфигурации
                            config_valid = await service.validate_server_config()
                            vpn_checks[protocol_str] = {
                                "status": "pass" if config_valid else "fail",
                                "message": f"{protocol_str.upper()} configuration validation"
                            }
                
                except Exception as e:
                    vpn_checks[protocol_str] = {
                        "status": "fail",
                        "message": f"Error checking {protocol_str}: {str(e)}"
                    }
            
            health_status["checks"]["vpn_protocols"] = vpn_checks
            
            # Определяем общий статус
            all_checks = [health_status["checks"]["server_active"]]
            all_checks.extend(vpn_checks.values())
            
            if any(check["status"] == "fail" for check in all_checks):
                health_status["overall_status"] = "unhealthy"
                health_status["healthy"] = False
            elif any(check["status"] == "warn" for check in all_checks):
                health_status["overall_status"] = "degraded"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error checking server health {server_id}: {e}")
            return {
                "healthy": False,
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def get_server_protocols_status(self, server_id: int) -> Dict[str, Any]:
        """
        Получить статус протоколов сервера
        
        Args:
            server_id: ID сервера
            
        Returns:
            Dict[str, Any]: Статус протоколов
        """
        try:
            server = await self.repos.servers.get_by_id(server_id)
            if not server:
                return {}
            
            return await self.vpn_manager.get_server_protocols_status(server)
            
        except Exception as e:
            logger.error(f"Error getting server protocols status: {e}")
            return {}
    
    async def create_server(
        self,
        name: str,
        country: str,
        country_code: str,
        city: str,
        ip_address: str,
        domain: Optional[str] = None,
        supported_protocols: List[str] = None,
        primary_protocol: VpnProtocol = VpnProtocol.VLESS,
        max_users: int = 100,
        admin_id: Optional[int] = None
    ) -> Server:
        """
        Создать новый сервер
        
        Args:
            name: Название сервера
            country: Страна
            country_code: Код страны
            city: Город
            ip_address: IP адрес
            domain: Домен (опционально)
            supported_protocols: Поддерживаемые протоколы
            primary_protocol: Основной протокол
            max_users: Максимальное количество пользователей
            admin_id: ID администратора
            
        Returns:
            Server: Созданный сервер
        """
        try:
            if not supported_protocols:
                supported_protocols = ["vless"]
            
            server_data = {
                "name": name,
                "country": country,
                "country_code": country_code,
                "city": city,
                "ip_address": ip_address,
                "domain": domain,
                "supported_protocols": supported_protocols,
                "primary_protocol": primary_protocol,
                "max_users": max_users,
                "is_active": True
            }
            
            server = Server(**server_data)
            self.session.add(server)
            await self.session.flush()
            await self.session.refresh(server)
            
            # Логируем создание сервера
            if admin_id:
                await self.repos.user_activities.log_activity(
                    user_id=admin_id,
                    action="server_created",
                    details={
                        "server_id": server.id,
                        "server_name": name,
                        "country": country,
                        "protocols": supported_protocols
                    }
                )
            
            await self.repos.commit()
            logger.info(f"Server created: {server.id} - {name}")
            
            return server
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error creating server: {e}")
            raise
    
    async def toggle_server_maintenance(
        self,
        server_id: int,
        maintenance_mode: bool,
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Переключить режим технического обслуживания
        
        Args:
            server_id: ID сервера
            maintenance_mode: Режим обслуживания
            admin_id: ID администратора
            
        Returns:
            bool: Успешность переключения
        """
        try:
            success = await self.repos.servers.update_stats(
                server_id,
                is_maintenance=maintenance_mode
            )
            
            if success and admin_id:
                await self.repos.user_activities.log_activity(
                    user_id=admin_id,
                    action="server_maintenance_toggled",
                    details={
                        "server_id": server_id,
                        "maintenance_mode": maintenance_mode,
                        "toggled_at": datetime.utcnow().isoformat()
                    }
                )
                await self.repos.commit()
            
            logger.info(f"Server {server_id} maintenance mode: {maintenance_mode}")
            return success
            
        except Exception as e:
            await self.repos.rollback()
            logger.error(f"Error toggling server maintenance: {e}")
            return False
    
    async def get_server_statistics(self, server_id: int, days: int = 7) -> Dict[str, Any]:
        """
        Получить статистику сервера за период
        
        Args:
            server_id: ID сервера
            days: Количество дней
            
        Returns:
            Dict[str, Any]: Статистика сервера
        """
        try:
            # Получаем статистику из базы данных
            stats = await self.repos.server_stats.get_server_stats(server_id, days * 24)
            
            if not stats:
                return {}
            
            # Агрегируем данные
            total_connections = sum(stat.active_connections for stat in stats)
            avg_cpu = sum(stat.cpu_usage for stat in stats) / len(stats)
            avg_memory = sum(stat.memory_usage for stat in stats) / len(stats)
            avg_disk = sum(stat.disk_usage for stat in stats) / len(stats)
            
            # Группируем по дням
            daily_stats = {}
            for stat in stats:
                day = stat.recorded_at.date()
                if day not in daily_stats:
                    daily_stats[day] = {
                        "connections": [],
                        "cpu": [],
                        "memory": [],
                        "disk": []
                    }
                
                daily_stats[day]["connections"].append(stat.active_connections)
                daily_stats[day]["cpu"].append(stat.cpu_usage)
                daily_stats[day]["memory"].append(stat.memory_usage)
                daily_stats[day]["disk"].append(stat.disk_usage)
            
            # Усредняем по дням
            for day_data in daily_stats.values():
                day_data["avg_connections"] = sum(day_data["connections"]) / len(day_data["connections"])
                day_data["avg_cpu"] = sum(day_data["cpu"]) / len(day_data["cpu"])
                day_data["avg_memory"] = sum(day_data["memory"]) / len(day_data["memory"])
                day_data["avg_disk"] = sum(day_data["disk"]) / len(day_data["disk"])
            
            return {
                "server_id": server_id,
                "period_days": days,
                "total_data_points": len(stats),
                "averages": {
                    "cpu_usage": round(avg_cpu, 2),
                    "memory_usage": round(avg_memory, 2),
                    "disk_usage": round(avg_disk, 2),
                    "connections": round(total_connections / len(stats), 2)
                },
                "daily_stats": daily_stats,
                "peak_connections": max(stat.active_connections for stat in stats),
                "peak_cpu": max(stat.cpu_usage for stat in stats)
            }
            
        except Exception as e:
            logger.error(f"Error getting server statistics: {e}")
            return {}


class ServerMonitoringService:
    """Сервис мониторинга серверов"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.server_service = ServerService(session)
    
    async def monitor_all_servers(self) -> Dict[str, Any]:
        """
        Мониторинг всех серверов
        
        Returns:
            Dict[str, Any]: Результаты мониторинга
        """
        try:
            servers = await self.repos.servers.get_all_active()
            
            monitoring_results = {
                "timestamp": datetime.utcnow().isoformat(),
                "total_servers": len(servers),
                "healthy_servers": 0,
                "degraded_servers": 0,
                "unhealthy_servers": 0,
                "servers": []
            }
            
            # Проверяем каждый сервер
            for server in servers:
                health_check = await self.server_service.check_server_health(server.id)
                
                server_status = {
                    "id": server.id,
                    "name": server.name,
                    "country": server.country,
                    "status": health_check.get("overall_status", "unknown"),
                    "healthy": health_check.get("healthy", False),
                    "load": await self.server_service._calculate_server_load(server),
                    "protocols": list(server.supported_protocols)
                }
                
                monitoring_results["servers"].append(server_status)
                
                # Подсчитываем статусы
                if health_check.get("overall_status") == "healthy":
                    monitoring_results["healthy_servers"] += 1
                elif health_check.get("overall_status") == "degraded":
                    monitoring_results["degraded_servers"] += 1
                else:
                    monitoring_results["unhealthy_servers"] += 1
            
            # Выявляем проблемы
            issues = []
            for server_status in monitoring_results["servers"]:
                if not server_status["healthy"]:
                    issues.append(f"Server {server_status['name']} is unhealthy")
                elif server_status["load"] > 0.9:
                    issues.append(f"Server {server_status['name']} is overloaded ({server_status['load']:.1%})")
            
            monitoring_results["issues"] = issues
            monitoring_results["has_issues"] = len(issues) > 0
            
            return monitoring_results
            
        except Exception as e:
            logger.error(f"Error monitoring servers: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def send_alerts_if_needed(self, monitoring_results: Dict[str, Any]):
        """
        Отправить уведомления при необходимости
        
        Args:
            monitoring_results: Результаты мониторинга
        """
        try:
            if not monitoring_results.get("has_issues"):
                return
            
            # Формируем сообщение об ошибках
            issues = monitoring_results.get("issues", [])
            if not issues:
                return
            
            alert_message = "🚨 Server Monitoring Alert\n\n"
            alert_message += f"Found {len(issues)} issues:\n"
            
            for issue in issues:
                alert_message += f"• {issue}\n"
            
            alert_message += f"\nTotal servers: {monitoring_results.get('total_servers', 0)}\n"
            alert_message += f"Healthy: {monitoring_results.get('healthy_servers', 0)}\n"
            alert_message += f"Unhealthy: {monitoring_results.get('unhealthy_servers', 0)}\n"
            
            # Отправляем уведомление администраторам
            from core.services.user_service import UserService
            user_service = UserService(self.session)
            await user_service.send_notification_to_admins(
                alert_message, 
                "server_monitoring"
            )
            
            logger.warning(f"Sent monitoring alert: {len(issues)} issues found")
            
        except Exception as e:
            logger.error(f"Error sending monitoring alerts: {e}")


class ServerLoadBalancer:
    """Балансировщик нагрузки серверов"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryManager(session)
        self.server_service = ServerService(session)
    
    async def get_optimal_server(
        self,
        user: User,
        protocol: Optional[VpnProtocol] = None,
        exclude_servers: List[int] = None
    ) -> Optional[Server]:
        """
        Получить оптимальный сервер с учетом балансировки
        
        Args:
            user: Пользователь
            protocol: Протокол
            exclude_servers: Исключить серверы
            
        Returns:
            Optional[Server]: Оптимальный сервер
        """
        try:
            # Получаем доступные серверы
            if protocol:
                servers = await self.repos.servers.get_by_protocol(protocol)
            else:
                servers = await self.repos.servers.get_all_active()
            
            # Исключаем серверы
            if exclude_servers:
                servers = [s for s in servers if s.id not in exclude_servers]
            
            if not servers:
                return None
            
            # Фильтруем по географии
            filtered_servers = await self._filter_by_geography(servers, user)
            
            # Выбираем сервер с учетом балансировки
            return await self._select_balanced_server(filtered_servers)
            
        except Exception as e:
            logger.error(f"Error getting optimal server: {e}")
            return None
    
    async def _filter_by_geography(self, servers: List[Server], user: User) -> List[Server]:
        """Фильтровать серверы по географии"""
        if user.country_code not in settings.RUSSIA_COUNTRY_CODES:
            return servers
        
        # Приоритетные страны для российских пользователей
        priority_countries = ["NL", "DE", "FI", "LV", "EE", "SE", "NO"]
        
        # Сначала ищем серверы в приоритетных странах
        priority_servers = [s for s in servers if s.country_code in priority_countries]
        if priority_servers:
            return priority_servers
        
        return servers
    
    async def _select_balanced_server(self, servers: List[Server]) -> Optional[Server]:
        """Выбрать сервер с учетом балансировки нагрузки"""
        if not servers:
            return None
        
        # Рассчитываем веса серверов
        server_weights = []
        for server in servers:
            load = await self.server_service._calculate_server_load(server)
            
            # Инвертируем нагрузку для веса (меньше нагрузка = больше вес)
            weight = 1.0 - load
            
            # Бонус за высокую производительность
            if server.max_users > 500:
                weight *= 1.2
            
            # Штраф за техническое обслуживание
            if server.is_maintenance:
                weight *= 0.1
            
            server_weights.append((server, max(weight, 0.01)))
        
        # Выбираем сервер методом взвешенного случайного выбора
        import random
        
        total_weight = sum(weight for _, weight in server_weights)
        if total_weight == 0:
            return servers[0]  # Возвращаем первый доступный
        
        random_value = random.uniform(0, total_weight)
        current_weight = 0
        
        for server, weight in server_weights:
            current_weight += weight
            if random_value <= current_weight:
                return server
        
        return servers[0]  # Fallback
    
    async def rebalance_users(self, from_server_id: int, to_server_id: int) -> int:
        """
        Перебалансировать пользователей между серверами
        
        Args:
            from_server_id: Исходный сервер
            to_server_id: Целевой сервер
            
        Returns:
            int: Количество перемещенных пользователей
        """
        try:
            # Получаем активные подписки на исходном сервере
            # Здесь нужен специальный метод в репозитории
            # subscriptions = await self.repos.subscriptions.get_by_server(from_server_id)
            
            migrated_count = 0
            
            # В реальной реализации здесь была бы логика миграции
            logger.info(f"Rebalanced {migrated_count} users from server {from_server_id} to {to_server_id}")
            
            return migrated_count
            
        except Exception as e:
            logger.error(f"Error rebalancing users: {e}")
            return 0